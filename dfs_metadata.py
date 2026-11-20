
import json
import os
import threading
import time
from concurrent import futures

import grpc
import dfs_pb2
import dfs_pb2_grpc
import net_config

REPLICATION_FACTOR = 2
HEARTBEAT_TIMEOUT = 6.0
STATE_FILE = "dfs_data/metadata.json"


class MetadataServicer(dfs_pb2_grpc.DfsMetadataServiceServicer):
    def __init__(self):
        self.lock = threading.Lock()
        self.clock = 0
        self.addresses = {}
        self.last_seen = {}
        self.files = {}
        self.pending_allocations = {}
        self._load()

    def log(self, msg):
        print(f"[meta t={self.clock:>3}] {msg}", flush=True)

    def _tick(self):
        self.clock += 1
        return self.clock

    def _update(self, received):
        self.clock = max(self.clock, received) + 1
        return self.clock

    def _load(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            self.files = data.get("files", {})
            self.addresses = data.get("addresses", {})
            self.clock = data.get("clock", 0)
            print(
                f"Loaded {len(self.files)} file(s) from {STATE_FILE}",
                flush=True
            )

    def _save(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({
                "clock": self.clock,
                "addresses": self.addresses,
                "files": self.files
            }, f)
        os.replace(tmp, STATE_FILE)

    def _alive(self, node_id):
        seen = self.last_seen.get(node_id)
        return (
            seen is not None
            and time.time() - seen <= HEARTBEAT_TIMEOUT
        )

    def _chunk_counts(self):
        counts = {}
        for rec in self.files.values():
            for chunk in rec["chunks"]:
                for node_id in chunk["nodes"]:
                    counts[node_id] = counts.get(node_id, 0) + 1
        return counts

    def _file_info(self, filename, rec):
        chunks = []

        for ch in rec["chunks"]:
            nodes = sorted(
                ch["nodes"],
                key=lambda n: 0 if self._alive(n) else 1
            )

            chunks.append(dfs_pb2.DfsChunkPlan(
                index=ch["index"],
                chunk_id=ch["chunk_id"],
                sha256=ch["sha256"],
                node_ids=nodes,
                addresses=[
                    self.addresses.get(n, "") for n in nodes
                ],
                alive=[self._alive(n) for n in nodes]
            ))

        return dfs_pb2.DfsFileInfo(
            found=True,
            filename=filename,
            version=rec["version"],
            size=rec["size"],
            sha256=rec["sha256"],
            chunks=chunks
        )

    def Heartbeat(self, request, context):
        with self.lock:
            is_new = request.node_id not in self.last_seen
            self.last_seen[request.node_id] = time.time()

            if self.addresses.get(request.node_id) != request.address:
                self.addresses[request.node_id] = request.address
                self._save()

            if is_new:
                self.log(
                    f"Node {request.node_id} registered "
                    f"at {request.address}"
                )

        return dfs_pb2.DfsAck(ok=True, message="ok")

    def AllocateFile(self, request, context):
        with self.lock:
            self._update(request.lamport_timestamp)

            if not request.filename or request.num_chunks <= 0:
                return dfs_pb2.DfsAllocateReply(
                    ok=False,
                    message="invalid filename or chunk count",
                    lamport_timestamp=self.clock
                )

            live = [
                n for n in self.addresses if self._alive(n)
            ]

            if not live:
                return dfs_pb2.DfsAllocateReply(
                    ok=False,
                    message="no live storage nodes",
                    lamport_timestamp=self.clock
                )

            if len(live) < REPLICATION_FACTOR:
                return dfs_pb2.DfsAllocateReply(
                    ok=False,
                    message="not enough live storage nodes for replication",
                    lamport_timestamp=self.clock
                )

            version = self._tick()
            replicas = REPLICATION_FACTOR
            counts = self._chunk_counts()
            load = {n: counts.get(n, 0) for n in live}

            plan = []

            for i in range(request.num_chunks):
                chosen = sorted(
                    live, key=lambda n: (load[n], n)
                )[:replicas]

                for node_id in chosen:
                    load[node_id] += 1

                plan.append(dfs_pb2.DfsChunkPlan(
                    index=i,
                    chunk_id=f"{request.filename}.v{version}.c{i}",
                    node_ids=chosen,
                    addresses=[
                        self.addresses[n] for n in chosen
                    ]
                ))

            self.pending_allocations[(request.filename, version)] = plan

            self.log(
                f"Allocated '{request.filename}' v{version}: "
                f"{request.num_chunks} chunk(s), "
                f"{replicas} replica(s) each"
            )

            return dfs_pb2.DfsAllocateReply(
                ok=True,
                message="allocated",
                version=version,
                plan=plan,
                lamport_timestamp=self.clock
            )

    def CommitFile(self, request, context):
        with self.lock:
            allocated_plan = self.pending_allocations.get(
                (request.filename, request.version)
            )
            if allocated_plan is None or len(request.chunks) != len(allocated_plan):
                return dfs_pb2.DfsCommitReply(
                    ok=False,
                    message="file commit does not match an allocation",
                    lamport_timestamp=self.clock
                )

            for expected, received in zip(
                allocated_plan,
                sorted(request.chunks, key=lambda chunk: chunk.index)
            ):
                if (
                    received.index != expected.index
                    or received.chunk_id != expected.chunk_id
                    or set(received.node_ids) != set(expected.node_ids)
                ):
                    return dfs_pb2.DfsCommitReply(
                        ok=False,
                        message="file commit does not match its allocated chunks",
                        lamport_timestamp=self.clock
                    )

            if any(
                len(ch.node_ids) != REPLICATION_FACTOR
                or len(set(ch.node_ids)) != REPLICATION_FACTOR
                for ch in request.chunks
            ):
                return dfs_pb2.DfsCommitReply(
                    ok=False,
                    message="a chunk does not have the configured replica count",
                    lamport_timestamp=self.clock
                )

            self.files[request.filename] = {
                "version": request.version,
                "size": request.size,
                "sha256": request.sha256,
                "chunks": [
                    {
                        "index": ch.index,
                        "chunk_id": ch.chunk_id,
                        "sha256": ch.sha256,
                        "nodes": list(ch.node_ids)
                    }
                    for ch in sorted(
                        request.chunks, key=lambda c: c.index
                    )
                ]
            }

            ts = self._tick()
            self._save()
            del self.pending_allocations[(request.filename, request.version)]

            self.log(
                f"Committed '{request.filename}' "
                f"v{request.version} ({request.size} bytes)"
            )

            return dfs_pb2.DfsCommitReply(
                ok=True,
                message="committed",
                lamport_timestamp=ts
            )

    def GetFileInfo(self, request, context):
        with self.lock:
            rec = self.files.get(request.filename)

            if rec is None:
                return dfs_pb2.DfsFileInfo(
                    found=False,
                    filename=request.filename
                )

            return self._file_info(request.filename, rec)

    def ClusterStatus(self, request, context):
        with self.lock:
            counts = self._chunk_counts()

            nodes = [
                dfs_pb2.DfsNodeStatus(
                    node_id=n,
                    address=a,
                    alive=self._alive(n),
                    chunk_count=counts.get(n, 0)
                )
                for n, a in sorted(self.addresses.items())
            ]

            files = [
                self._file_info(fn, rec)
                for fn, rec in sorted(self.files.items())
            ]

        return dfs_pb2.DfsStatusReply(
            nodes=nodes,
            files=files
        )

    def AddReplica(self, request, context):
        with self.lock:
            rec = self.files.get(request.filename)

            if rec is None:
                return dfs_pb2.DfsAck(
                    ok=False, message="unknown file"
                )

            for ch in rec["chunks"]:
                if ch["index"] == request.chunk_index:
                    if request.node_id in ch["nodes"]:
                        return dfs_pb2.DfsAck(
                            ok=True, message="replica already recorded"
                        )

                    if len(ch["nodes"]) >= REPLICATION_FACTOR:
                        stale_nodes = [
                            node_id for node_id in ch["nodes"]
                            if not self._alive(node_id)
                        ]
                        if not stale_nodes:
                            return dfs_pb2.DfsAck(
                                ok=False,
                                message="chunk already has the replica count",
                            )
                        ch["nodes"].remove(stale_nodes[0])

                    ch["nodes"].append(request.node_id)
                    self._save()

                    self.log(
                        f"Replica of '{request.filename}' "
                        f"chunk {request.chunk_index} "
                        f"recorded on {request.node_id}"
                    )

                    return dfs_pb2.DfsAck(
                        ok=True, message="replica recorded"
                    )

            return dfs_pb2.DfsAck(
                ok=False, message="unknown chunk"
            )

    def monitor(self):
        reported = {}

        while True:
            time.sleep(1)

            with self.lock:
                for node_id in list(self.addresses):
                    alive = self._alive(node_id)
                    previous = reported.get(node_id)
                    reported[node_id] = alive

                    if previous is not None and previous != alive:
                        state = (
                            "BACK UP" if alive
                            else "DOWN (no heartbeat)"
                        )
                        self.log(f"Node {node_id} is {state}")


def serve():
    address = net_config.resolve("dfs-meta")
    port = address.split(":")[1]

    servicer = MetadataServicer()
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10)
    )

    dfs_pb2_grpc.add_DfsMetadataServiceServicer_to_server(
        servicer, server
    )

    server.add_insecure_port(f"{net_config.bind_host()}:{port}")
    server.start()

    print(
        f"DFS metadata server listening on {address} "
        f"(replication factor {REPLICATION_FACTOR})",
        flush=True
    )

    threading.Thread(
        target=servicer.monitor, daemon=True
    ).start()

    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    serve()

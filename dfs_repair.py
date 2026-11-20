
import hashlib
import sys
import grpc

import dfs_pb2
import dfs_pb2_grpc
import net_config

REPLICATION_FACTOR = 2


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def repair():
    try:
        with grpc.insecure_channel(
            net_config.resolve("dfs-meta")
        ) as channel:
            meta = dfs_pb2_grpc.DfsMetadataServiceStub(channel)
            status = meta.ClusterStatus(
                dfs_pb2.DfsStatusRequest(), timeout=5
            )

            alive = {
                n.node_id: n.address
                for n in status.nodes if n.alive
            }

            print(f"Live nodes: {', '.join(sorted(alive)) or 'none'}")

            copied = 0
            problems = 0

            for file_info in status.files:
                for chunk in sorted(
                    file_info.chunks, key=lambda c: c.index
                ):
                    healthy_holders = []
                    repair_targets = []

                    for node_id, address, is_alive in zip(
                        chunk.node_ids,
                        chunk.addresses,
                        chunk.alive
                    ):
                        if not is_alive:
                            continue

                        try:
                            with grpc.insecure_channel(address) as sch:
                                stub = dfs_pb2_grpc.DfsStorageServiceStub(sch)
                                result = stub.GetChunk(
                                    dfs_pb2.DfsChunkId(
                                        chunk_id=chunk.chunk_id
                                    ),
                                    timeout=3
                                )
                        except grpc.RpcError:
                            repair_targets.append(node_id)
                            continue

                        if sha256(result.data) == chunk.sha256:
                            healthy_holders.append(node_id)
                        else:
                            repair_targets.append(node_id)

                    missing = REPLICATION_FACTOR - len(healthy_holders)

                    if missing <= 0:
                        continue

                    if not healthy_holders:
                        print(
                            f"   {file_info.filename} chunk "
                            f"{chunk.index}: NO healthy live replica, "
                            "cannot repair"
                        )
                        problems += 1
                        continue

                    data = None

                    # Read a valid copy before overwriting or creating replicas.
                    for node_id in healthy_holders:
                        address = alive.get(node_id)
                        if not address:
                            continue

                        try:
                            with grpc.insecure_channel(address) as sch:
                                stub = dfs_pb2_grpc.DfsStorageServiceStub(sch)
                                result = stub.GetChunk(
                                    dfs_pb2.DfsChunkId(
                                        chunk_id=chunk.chunk_id
                                    ),
                                    timeout=3
                                )

                            if sha256(result.data) == chunk.sha256:
                                data = result.data
                                break

                        except grpc.RpcError:
                            continue

                    if data is None:
                        print(
                            f"     {file_info.filename} chunk "
                            f"{chunk.index}: no healthy copy to repair from"
                        )
                        problems += 1
                        continue

                    targets = list(dict.fromkeys(repair_targets))
                    targets.extend(
                        node_id for node_id in sorted(alive)
                        if node_id not in healthy_holders
                        and node_id not in targets
                    )

                    for target in targets[:missing]:
                        try:
                            with grpc.insecure_channel(
                                alive[target]
                            ) as sch:
                                stub = dfs_pb2_grpc.DfsStorageServiceStub(sch)
                                ack = stub.PutChunk(
                                    dfs_pb2.DfsChunkData(
                                        chunk_id=chunk.chunk_id,
                                        data=data,
                                        sha256=chunk.sha256
                                    ),
                                    timeout=5
                                )

                            if not ack.ok:
                                problems += 1
                                continue

                            if target not in chunk.node_ids:
                                recorded = meta.AddReplica(
                                    dfs_pb2.DfsReplicaUpdate(
                                        filename=file_info.filename,
                                        chunk_index=chunk.index,
                                        node_id=target
                                    ),
                                    timeout=5
                                )
                                if not recorded.ok:
                                    print(
                                        f"Could not record replica on {target}"
                                    )
                                    problems += 1
                                    continue

                            print(
                                f"     {file_info.filename} chunk "
                                f"{chunk.index}: repaired on {target}"
                            )
                            copied += 1

                        except grpc.RpcError as e:
                            print(
                                f"     {file_info.filename} chunk "
                                f"{chunk.index}: could not copy to "
                                f"{target} ({e.code().name})"
                            )
                            problems += 1

            print(
                f"Repair finished: {copied} chunk copy(ies) made, "
                f"{problems} problem(s)."
            )
            return problems

    except grpc.RpcError as e:
        print(
            f"Could not reach the metadata server ({e.code().name})."
        )
        return 1


if __name__ == "__main__":
    sys.exit(1 if repair() else 0)


import hashlib
import os
import sys
import grpc

import dfs_pb2
import dfs_pb2_grpc
import net_config

CHUNK_SIZE = int(os.environ.get("DFS_CHUNK_SIZE", 64 * 1024))
CLOCK_FILE = ".dfs_client_clock"


class DfsClientError(Exception):
    """Raised when a distributed file operation cannot be completed."""


class DfsFileNotFound(DfsClientError):
    """Raised when the metadata service has no committed file record."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_clock():
    try:
        with open(CLOCK_FILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def save_clock(value):
    with open(CLOCK_FILE, "w", encoding="utf-8") as f:
        f.write(str(value))


def meta_channel():
    return grpc.insecure_channel(net_config.resolve("dfs-meta"))


def store_bytes(filename, data):
    """Store bytes as a committed DFS file and return its stable identifier."""
    if (
        not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
    ):
        raise DfsClientError("Invalid DFS file identifier.")
    pieces = [
        data[i:i + CHUNK_SIZE]
        for i in range(0, len(data), CHUNK_SIZE)
    ] or [b""]

    clock = load_clock() + 1

    try:
        with meta_channel() as channel:
            meta = dfs_pb2_grpc.DfsMetadataServiceStub(channel)

            reply = meta.AllocateFile(
                dfs_pb2.DfsAllocateRequest(
                    filename=filename,
                    num_chunks=len(pieces),
                    lamport_timestamp=clock
                ),
                timeout=5
            )

            if not reply.ok:
                raise DfsClientError("DFS did not allocate storage for the report.")

            clock = max(clock, reply.lamport_timestamp) + 1

            committed = []

            for plan in reply.plan:
                if (
                    len(plan.node_ids) == 0
                    or len(set(plan.node_ids)) != len(plan.node_ids)
                ):
                    raise DfsClientError(
                        "DFS returned an invalid replica plan."
                    )
                piece = pieces[plan.index]
                digest = sha256(piece)
                stored_on = []

                for node_id, addr in zip(
                    plan.node_ids, plan.addresses
                ):
                    try:
                        with grpc.insecure_channel(addr) as sch:
                            stub = dfs_pb2_grpc.DfsStorageServiceStub(sch)
                            ack = stub.PutChunk(
                                dfs_pb2.DfsChunkData(
                                    chunk_id=plan.chunk_id,
                                    data=piece,
                                    sha256=digest
                                ),
                                timeout=5
                            )

                        if ack.ok:
                            stored_on.append(node_id)
                    except grpc.RpcError:
                        continue

                if len(stored_on) != len(plan.node_ids):
                    raise DfsClientError(
                        "DFS could not store every report chunk replica."
                    )

                committed.append(
                    dfs_pb2.DfsChunkPlan(
                        index=plan.index,
                        chunk_id=plan.chunk_id,
                        sha256=digest,
                        node_ids=stored_on
                    )
                )

            done = meta.CommitFile(
                dfs_pb2.DfsCommitRequest(
                    filename=filename,
                    version=reply.version,
                    size=len(data),
                    sha256=sha256(data),
                    chunks=committed
                ),
                timeout=5
            )

            if not done.ok:
                raise DfsClientError("DFS could not commit the report.")

            clock = max(clock, done.lamport_timestamp) + 1
            try:
                save_clock(clock)
            except OSError as error:
                print(
                    f"Warning: could not persist the DFS client clock: {error}",
                    file=sys.stderr,
                )

    except grpc.RpcError as error:
        raise DfsClientError("DFS services are unavailable.") from error

    return filename


def put(path):
    with open(path, "rb") as file_obj:
        data = file_obj.read()
    return store_bytes(os.path.basename(path), data)


def fetch_bytes(filename):
    """Fetch and checksum-verify a committed DFS file."""
    try:
        with meta_channel() as channel:
            meta = dfs_pb2_grpc.DfsMetadataServiceStub(channel)
            info = meta.GetFileInfo(
                dfs_pb2.DfsFileQuery(filename=filename),
                timeout=5
            )

    except grpc.RpcError as error:
        raise DfsClientError("DFS services are unavailable.") from error

    if not info.found:
        raise DfsFileNotFound("DFS report was not found.")

    parts = []

    for chunk in sorted(info.chunks, key=lambda c: c.index):
        data = None

        for node_id, addr in zip(chunk.node_ids, chunk.addresses):
            if not addr:
                continue

            try:
                with grpc.insecure_channel(addr) as sch:
                    stub = dfs_pb2_grpc.DfsStorageServiceStub(sch)
                    reply = stub.GetChunk(
                        dfs_pb2.DfsChunkId(
                            chunk_id=chunk.chunk_id
                        ),
                        timeout=3
                    )

            except grpc.RpcError:
                continue

            if sha256(reply.data) != chunk.sha256:
                continue

            data = reply.data
            break

        if data is None:
            raise DfsClientError(
                "No healthy DFS replica is available for the report."
            )

        parts.append(data)

    blob = b"".join(parts)

    if sha256(blob) != info.sha256:
        raise DfsClientError("DFS report checksum verification failed.")

    return blob


def get(filename, out_path):
    blob = fetch_bytes(filename)
    with open(out_path, "wb") as file_obj:
        file_obj.write(blob)
    return out_path


def status():
    try:
        with meta_channel() as channel:
            stub = dfs_pb2_grpc.DfsMetadataServiceStub(channel)
            reply = stub.ClusterStatus(
                dfs_pb2.DfsStatusRequest(),
                timeout=5
            )

    except grpc.RpcError as e:
        print(
            f"Could not reach the metadata server ({e.code().name}). "
            "Is dfs_metadata.py running?"
        )
        return

    print("Storage nodes:")

    for node in reply.nodes:
        state = "UP     " if node.alive else "DOWN"
        print(
            f"     {node.node_id}    {state}   {node.address}   "
            f"chunks held: {node.chunk_count}"
        )

    print("Files:")

    if not reply.files:
        print("     (none)")

    for file_info in reply.files:
        print(
            f"     {file_info.filename}    v{file_info.version}   "
            f"{file_info.size} bytes   {len(file_info.chunks)} chunk(s)"
        )

        for chunk in sorted(file_info.chunks, key=lambda c: c.index):
            where = ", ".join(
                f"{node_id}{'' if alive else ' (down)'}"
                for node_id, alive in zip(
                    chunk.node_ids, chunk.alive
                )
            )
            print(f"       chunk {chunk.index}: {where}")


if __name__ == "__main__":
    args = sys.argv[1:]

    try:
        if len(args) == 2 and args[0] == "put":
            print(put(args[1]))
        elif len(args) == 3 and args[0] == "get":
            print(get(args[1], args[2]))
        elif len(args) == 1 and args[0] == "status":
            status()
        else:
            print(
                "Usage:\n"
                "  python dfs_client.py put <path>\n"
                "  python dfs_client.py get <filename> <output_path>\n"
                "  python dfs_client.py status"
            )
    except (DfsClientError, OSError) as error:
        print(f"DFS operation failed: {error}", file=sys.stderr)
        sys.exit(1)

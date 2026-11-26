"""Serve a numeric GitHub release and pullable OCI index on isolated loopback TLS."""

import gzip
import hashlib
import http.server
import io
import json
from pathlib import Path
import ssl
import tarfile
import threading

REPO = "ghcr.io/myflow-xyz/ci-go"
VERSION = "2.3.4"


class ReleaseServer:
    def __init__(self, bundle_version=None):
        routes = {}
        prefix = "/v2/myflow-xyz/ci-go"
        if bundle_version:
            project = "/myflow-xyz/ci-images"
            tag = "v" + bundle_version
            installer = Path("/workspace/scripts/ci-utils/install.sh")
            routes[f"{project}/{tag}/scripts/ci-utils/install.sh"] = (
                "text/plain",
                installer.read_bytes(),
                None,
            )
            for asset in Path("/assets").glob(f"ci-utils_{bundle_version}_*"):
                routes[f"{project}/releases/download/{tag}/{asset.name}"] = (
                    "application/octet-stream",
                    asset.read_bytes(),
                    None,
                )

        def store(kind, data, collection):
            if not isinstance(data, bytes):
                data = json.dumps(data).encode()
            digest = "sha256:" + hashlib.sha256(data).hexdigest()
            routes[f"{prefix}/{collection}/{digest}"] = (kind, data, digest)
            return dict(mediaType=kind, size=len(data), digest=digest)

        layer = io.BytesIO()
        with tarfile.open(fileobj=layer, mode="w") as tar:
            tar.addfile(tarfile.TarInfo("release-marker"))
        data = layer.getvalue()
        blob = store(
            "application/vnd.oci.image.layer.v1.tar+gzip", gzip.compress(data), "blobs"
        )
        manifests = []
        for arch in ("amd64", "arm64"):
            config = store(
                "application/vnd.oci.image.config.v1+json",
                dict(
                    architecture=arch,
                    os="linux",
                    config={},
                    rootfs=dict(
                        type="layers",
                        diff_ids=["sha256:" + hashlib.sha256(data).hexdigest()],
                    ),
                ),
                "blobs",
            )
            kind = "application/vnd.oci.image.manifest.v1+json"
            manifest = store(
                kind,
                dict(schemaVersion=2, mediaType=kind, config=config, layers=[blob]),
                "manifests",
            )
            manifests.append(
                dict(**manifest, platform=dict(os="linux", architecture=arch))
            )
        kind = "application/vnd.oci.image.index.v1+json"
        index = dict(
            schemaVersion=2,
            mediaType=kind,
            manifests=manifests,
        )
        self.digest = store(kind, index, "manifests")["digest"]
        good = routes[f"{prefix}/manifests/{self.digest}"]
        routes[f"{prefix}/manifests/latest"] = good
        tag = f"{prefix}/manifests/{VERSION}"
        routes[tag] = good
        other = store(
            kind, dict(**index, annotations={"fixture": "mismatch"}), "manifests"
        )["digest"]
        self.mismatch = lambda: routes.update(
            {tag: routes[f"{prefix}/manifests/{other}"]}
        )
        release = dict(
            tag_name="v" + VERSION,
            draft=False,
            prerelease=False,
            body=f"| {REPO}:{VERSION} | {self.digest} |",
        )
        routes["/repos/myflow-xyz/ci-images/releases"] = (
            "application/json",
            json.dumps([release]).encode(),
            None,
        )
        routes["/v2/"] = ("application/json", b"{}", None)

        class Handler(http.server.BaseHTTPRequestHandler):
            def respond(self):
                path = self.path.partition("?")[0]
                if path not in routes:
                    self.send_error(404)
                    return
                kind, data, digest = routes[path]
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                if digest:
                    self.send_header("Docker-Content-Digest", digest)
                self.end_headers()
                if self.command == "GET":
                    self.wfile.write(data)

            do_GET = do_HEAD = respond

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 443), Handler)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain("/fixture-tls/ca.crt", "/fixture-tls/key.pem")
        self.server.socket = tls.wrap_socket(self.server.socket, server_side=True)

    def __enter__(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

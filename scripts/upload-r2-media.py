#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import hmac
import mimetypes
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_EXTENSIONS = (".webp", ".mp4")
DEFAULT_CACHE_CONTROL = "public, max-age=86400"
SERVICE = "s3"
REGION = "auto"


def hmac_sha256(key, message):
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret_key, date_stamp):
    date_key = hmac_sha256(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    region_key = hmac_sha256(date_key, REGION)
    service_key = hmac_sha256(region_key, SERVICE)
    return hmac_sha256(service_key, "aws4_request")


def content_type_for(path):
    if path.suffix == ".webp":
        return "image/webp"
    if path.suffix == ".mp4":
        return "video/mp4"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def canonicalize_headers(headers):
    pairs = sorted((name.lower(), " ".join(value.strip().split())) for name, value in headers.items())
    canonical = "".join(f"{name}:{value}\n" for name, value in pairs)
    signed = ";".join(name for name, _ in pairs)
    return canonical, signed


def sign_request(method, host, path, headers, payload_hash, secret_key, access_key_id, amz_date, date_stamp):
    canonical_headers, signed_headers = canonicalize_headers(headers)
    canonical_request = "\n".join(
        [
            method,
            path,
            "",
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(
        signing_key(secret_key, date_stamp),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )


def upload_file(path, args):
    account_id = args.account_id
    bucket = args.bucket
    host = f"{account_id}.r2.cloudflarestorage.com"
    key = f"{args.prefix.rstrip('/')}/{path.name}" if args.prefix else path.name
    request_path = f"/{quote(bucket, safe='')}/{quote(key, safe='/')}"
    url = f"https://{host}{request_path}"
    body = path.read_bytes()
    payload_hash = hashlib.sha256(body).hexdigest()
    now = dt.datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    headers = {
        "Cache-Control": args.cache_control,
        "Content-Type": content_type_for(path),
        "Host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    headers["Authorization"] = sign_request(
        "PUT",
        host,
        request_path,
        headers,
        payload_hash,
        args.secret_access_key,
        args.access_key_id,
        amz_date,
        date_stamp,
    )
    if args.dry_run:
        print(f"DRY RUN {path} -> s3://{bucket}/{key}")
        return
    request = Request(url, data=body, headers=headers, method="PUT")
    try:
        with urlopen(request, timeout=args.timeout) as response:
            status = response.status
            if status not in (200, 201, 204):
                raise RuntimeError(f"Unexpected HTTP {status} for {path}")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Upload failed for {path}: HTTP {error.code}\n{detail}") from error
    public_url = ""
    if args.public_base_url:
        public_url = f" -> {args.public_base_url.rstrip('/')}/{quote(key, safe='/')}"
    print(f"Uploaded {path.name}{public_url}")


def find_default_files(root):
    files = []
    for extension in DEFAULT_EXTENSIONS:
        files.extend(sorted(root.glob(f"*{extension}")))
    return files


def parse_args():
    parser = argparse.ArgumentParser(description="Upload portfolio media to Cloudflare R2.")
    parser.add_argument("files", nargs="*", type=Path, help="Media files to upload. Defaults to root .webp and .mp4 files.")
    parser.add_argument("--prefix", default=os.getenv("R2_PREFIX", ""), help="Optional object prefix, for example media.")
    parser.add_argument("--bucket", default=os.getenv("R2_BUCKET", "yoesells-media"))
    parser.add_argument("--account-id", default=os.getenv("R2_ACCOUNT_ID"))
    parser.add_argument("--access-key-id", default=os.getenv("R2_ACCESS_KEY_ID"))
    parser.add_argument("--secret-access-key", default=os.getenv("R2_SECRET_ACCESS_KEY"))
    parser.add_argument("--public-base-url", default=os.getenv("R2_PUBLIC_BASE_URL"))
    parser.add_argument("--cache-control", default=os.getenv("R2_CACHE_CONTROL", DEFAULT_CACHE_CONTROL))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    missing = [
        name
        for name, value in (
            ("R2_ACCOUNT_ID", args.account_id),
            ("R2_ACCESS_KEY_ID", args.access_key_id),
            ("R2_SECRET_ACCESS_KEY", args.secret_access_key),
        )
        if not value
    ]
    if missing:
        raise SystemExit("Missing required environment values: " + ", ".join(missing))
    files = args.files or find_default_files(Path.cwd())
    if not files:
        raise SystemExit("No media files found.")
    for file_path in files:
        if not file_path.is_file():
            raise SystemExit(f"Not a file: {file_path}")
    for file_path in files:
        upload_file(file_path, args)


if __name__ == "__main__":
    main()

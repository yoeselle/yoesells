# R2 Media Workflow

Bucket: `yoesells-media`

Public base URL:

```text
https://pub-9be06382f89147958a8fa7ab2737bb5d.r2.dev
```

This is Cloudflare's Public Development URL. It works for the current site, but a custom media domain is better for production.

The upload script uses temporary environment variables and does not save credentials.

```sh
export R2_ACCOUNT_ID="f617d7da7c9b9e1012f6dd9a99ce935a"
export R2_BUCKET="yoesells-media"
export R2_PUBLIC_BASE_URL="https://pub-9be06382f89147958a8fa7ab2737bb5d.r2.dev"
export R2_ACCESS_KEY_ID="..."
export R2_SECRET_ACCESS_KEY="..."
python3 scripts/upload-r2-media.py
```

By default it uploads root-level `.webp` and `.mp4` files, preserving the filenames used by `index.html`.

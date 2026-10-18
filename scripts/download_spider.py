"""下载固定版本 Spider 公开数据；记录来源并校验哈希。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_PAGE = "https://yale-lily.github.io/spider"
FILE_ID = "1403EGqzIDoHMdQF4c9Bkyl7dZLZ5Wt6J"
OFFICIAL_URL = f"https://drive.usercontent.google.com/download?id={FILE_ID}&export=download&confirm=t"
MIRROR_URL = ("https://huggingface.co/datasets/xlangai/spider/resolve/"
              "eb27f6b14c95967490e458ab29803597d70366ba/data/spider.zip")
MIRROR_SHA256 = "5ddff97bb1d421282c593e8d30ce0ce107270f4dd4a21d60eba4bf287d5956b1"


def validate_dataset(path: Path) -> None:
    for name in ("dev.json", "tables.json", "train_spider.json"):
        if not (path / name).is_file():
            raise ValueError(f"缺少 {path / name}")
    dev = json.loads((path / "dev.json").read_text())
    for db_id in {row["db_id"] for row in dev}:
        if not (path / "database" / db_id / f"{db_id}.sqlite").is_file():
            raise ValueError(f"缺少 dev 数据库: {db_id}")


def extract_dataset(archive: Path, destination: Path) -> None:
    # 拒绝路径穿越与符号链接；先验证完整性再搬入最终目录。
    with tempfile.TemporaryDirectory(dir=ROOT / "work") as scratch:
        scratch_path = Path(scratch)
        with zipfile.ZipFile(archive) as bundle:
            total = sum(item.file_size for item in bundle.infolist())
            if total > 8 * 1024**3:
                raise ValueError("压缩包解压体积超过 8 GiB，请人工检查")
            for item in bundle.infolist():
                target = (scratch_path / item.filename).resolve()
                if not target.is_relative_to(scratch_path.resolve()):
                    raise ValueError("压缩包含越界路径")
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError("压缩包含符号链接")
            bundle.extractall(scratch_path)
        candidates = [p.parent for p in scratch_path.rglob("dev.json")]
        valid = []
        for candidate in candidates:
            try:
                validate_dataset(candidate)
                valid.append(candidate)
            except ValueError:
                continue
        if len(valid) != 1:
            raise ValueError("未找到唯一且完整的 Spider 1.0 数据目录")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ValueError("目标目录已存在，请检查内容，不自动覆盖")
        shutil.move(str(valid[0]), str(destination))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["mirror", "official"], default="mirror")
    parser.add_argument("--archive", type=Path, help="导入手动下载的官方 zip")
    parser.add_argument("--destination", type=Path, default=ROOT / "data/spider")
    args = parser.parse_args()
    (ROOT / "work").mkdir(exist_ok=True)
    archive = args.archive or ROOT / "work/spider_data.zip"
    download_url = MIRROR_URL if args.source == "mirror" else OFFICIAL_URL
    try:
        if args.destination.exists():
            validate_dataset(args.destination)
            print(f"已有完整数据：{args.destination}")
            return 0
        if args.archive is None:
            print(f"正在下载：{download_url}", flush=True)
            request = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as out:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 2 * 1024**3:
                        raise ValueError("下载超过 2 GiB，停止")
                    out.write(chunk)
        if not zipfile.is_zipfile(archive):
            raise ValueError("下载内容不是 ZIP，可能需要登录或人工确认")
        with archive.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if args.source == "mirror" and digest != MIRROR_SHA256:
            raise ValueError("固定镜像 SHA-256 不匹配，请核对数据来源")
        extract_dataset(archive, args.destination)
        manifest = {
            "source": OFFICIAL_PAGE,
            "download_url": download_url,
            "downloaded_at": datetime.now(UTC).isoformat(),
            "archive_sha256": digest,
            "license": "CC BY-SA 4.0",
        }
        (args.destination / "download_manifest.json").write_text(json.dumps(manifest, indent=2))
        print(f"已验证并解压：{args.destination}")
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"下载或校验失败：{error}")
        print(f"可从 {OFFICIAL_PAGE} 手动下载 Spider Dataset，")
        print(f"解压到 {args.destination}，或使用 --archive /路径/spider_data.zip 导入。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

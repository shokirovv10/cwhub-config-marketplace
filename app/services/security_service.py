from pathlib import Path
from zipfile import ZipFile, BadZipFile
import hashlib

BLOCKED_ARCHIVE_EXTENSIONS = {'.exe','.dll','.bat','.cmd','.com','.scr','.msi','.ps1','.vbs','.js','.jar','.sh'}


def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def scan_config_file(path, original_name):
    p=Path(path)
    ext=p.suffix.lower()
    if ext in {'.zip'}:
        try:
            with ZipFile(p) as z:
                for name in z.namelist():
                    suffix=Path(name).suffix.lower()
                    if suffix in BLOCKED_ARCHIVE_EXTENSIONS:
                        return False, f'Arxiv ichida taqiqlangan fayl turi topildi: {suffix}'
        except BadZipFile:
            return False, 'ZIP fayl buzilgan yoki noto‘g‘ri arxiv.'
    if ext in BLOCKED_ARCHIVE_EXTENSIONS:
        return False, 'Bu fayl turi ruxsat etilmagan.'
    return True, ''

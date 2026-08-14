from pathlib import Path
from uuid import uuid4
import json
import shutil
from werkzeug.utils import secure_filename
from flask import current_app

class LocalStorage:
    def save(self, fileobj, folder, original_name):
        safe = secure_filename(original_name) or 'file'
        name = f'{uuid4().hex}_{safe}'
        root = Path(current_app.config['UPLOAD_FOLDER']) / folder
        root.mkdir(parents=True, exist_ok=True)
        path = root / name
        fileobj.save(path)
        return str(path), safe, path.stat().st_size

    def exists(self, path):
        return bool(path) and Path(path).is_file()

    def delete(self, path):
        if not path:
            return
        p = Path(path)
        try:
            if p.is_file(): p.unlink()
            elif p.is_dir(): shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass

    @property
    def temp_root(self):
        root = Path(current_app.config['UPLOAD_FOLDER']) / '_temp_chunks'
        root.mkdir(parents=True, exist_ok=True)
        return root

    def init_chunk(self, user_id, filename, size, mime, kind):
        safe = secure_filename(filename) or 'upload.bin'
        upload_id = uuid4().hex
        folder = self.temp_root / upload_id
        folder.mkdir(parents=True, exist_ok=False)
        meta = {'user_id': int(user_id), 'filename': safe, 'size': int(size), 'mime': mime or 'application/octet-stream', 'kind': kind, 'created': __import__('time').time()}
        (folder/'meta.json').write_text(json.dumps(meta), encoding='utf-8')
        return upload_id

    def write_chunk(self, upload_id, user_id, chunk_index, data):
        folder = self.temp_root / upload_id
        meta_path = folder / 'meta.json'
        if not meta_path.exists(): raise FileNotFoundError('upload sessiyasi topilmadi')
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        if int(meta['user_id']) != int(user_id): raise PermissionError('upload huquqi yo‘q')
        part = folder / f'part_{int(chunk_index):06d}'
        with part.open('wb') as f: f.write(data)
        return part.stat().st_size

    def complete_chunk(self, upload_id, user_id, total_chunks):
        folder = self.temp_root / upload_id
        meta_path = folder / 'meta.json'
        if not meta_path.exists(): raise FileNotFoundError('upload sessiyasi topilmadi')
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        if int(meta['user_id']) != int(user_id): raise PermissionError('upload huquqi yo‘q')
        target = self.temp_root / f'{upload_id}_{meta["filename"]}'
        with target.open('wb') as out:
            for i in range(int(total_chunks)):
                part = folder / f'part_{i:06d}'
                if not part.exists(): raise ValueError(f'{i}-qism yetishmayapti')
                with part.open('rb') as src: shutil.copyfileobj(src, out, length=1024*1024)
        for part in folder.glob('part_*'):
            try: part.unlink()
            except OSError: pass
        # Keep meta.json until the owner consumes the finished upload.
        return str(target), meta

    def consume_temp(self, upload_id, user_id, folder_name):
        folder = self.temp_root / upload_id
        meta_path = folder / 'meta.json'
        matches = list(self.temp_root.glob(upload_id + '_*'))
        finished = matches[0] if matches else None
        if not meta_path.exists() or not finished or not finished.is_file():
            raise FileNotFoundError('tayyor fayl topilmadi')
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        if int(meta['user_id']) != int(user_id):
            raise PermissionError('upload egasi mos emas')
        safe_name = secure_filename(meta.get('filename','file')) or 'file'
        dest_dir = Path(current_app.config['UPLOAD_FOLDER']) / folder_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f'{uuid4().hex}_{safe_name}'
        shutil.move(str(finished), str(dest))
        shutil.rmtree(folder, ignore_errors=True)
        return str(dest), safe_name, dest.stat().st_size


def storage():
    return LocalStorage()

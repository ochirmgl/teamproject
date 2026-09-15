import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import database
from preserve_data import snapshot, verify, restore_to_empty
from runtime_storage import data_root
from document_quality import inspect_coverage


class PreservationTests(unittest.TestCase):
    def test_snapshot_restore_and_new_code_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'source'
            root.mkdir()
            database.init_db(root/'dms_system.db')
            (root/'uploaded_files').mkdir()
            (root/'uploaded_files'/'x.txt').write_text('Keep document')
            with closing(database.open_database(root/'dms_system.db')) as conn, conn:
                conn.execute("INSERT INTO documents(title,file_path) VALUES ('Keep','uploaded_files/x.txt')")
                conn.execute("INSERT INTO chat_sessions(id,user_id,title) VALUES (1,1,'Keep chat')")
                conn.execute("INSERT INTO chat_messages(session_id,role,content) VALUES (1,'user','Keep question')")
            archive = Path(folder)/'snapshot.zip'
            self.assertEqual(snapshot(root,archive),2)
            self.assertTrue(verify(archive))
            restored = restore_to_empty(archive,Path(folder)/'restored')
            with patch.dict('os.environ',{'DMS_DATA_DIR':str(restored)}):
                self.assertEqual(data_root(Path(folder)/'new-code'),restored)
            database.init_db(restored/'dms_system.db')
            with closing(database.open_database(restored/'dms_system.db')) as conn:
                self.assertEqual(conn.execute('SELECT content FROM chat_messages').fetchone()[0],'Keep question')
            self.assertEqual((restored/'uploaded_files'/'x.txt').read_text(),'Keep document')
            with self.assertRaises(FileExistsError):
                restore_to_empty(archive,restored)
            with self.assertRaises(ValueError):
                snapshot(root,archive)

    def test_missing_document_refuses_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database.init_db(root/'dms_system.db')
            with closing(database.open_database(root/'dms_system.db')) as conn, conn:
                conn.execute("INSERT INTO documents(title,file_path) VALUES ('Missing','uploaded_files/missing.txt')")
            with self.assertRaises(ValueError):
                snapshot(root,root/'bad.zip')

    def test_page_coverage_and_appendix_warning(self):
        from pypdf import PdfWriter
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'one.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=200,height=200)
            writer.write(path)
            report = inspect_coverage(path,[('1-р хуудас','Журмыг хавсралтаар баталсугай.')],expected_pages=4)
            self.assertEqual(report['source_pages'],1)
            self.assertEqual(report['text_pages'],1)
            self.assertEqual(report['completeness'],'unverified')
            self.assertTrue(any('Хавсралт' in w for w in report['warnings']))
            self.assertTrue(any('таарахгүй' in w for w in report['warnings']))
            self.assertEqual(inspect_coverage(path,[])['text_pages'],0)

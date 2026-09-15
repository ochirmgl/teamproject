from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest
from pypdf import PdfWriter
from document_viewer import convert, page_image_html, render_document
from PIL import Image


class ViewerTests(unittest.TestCase):
    def test_zoom_changes_display_width(self):
        image = Image.new('RGB',(20,30),'white')
        self.assertIn('width:100%', page_image_html(image,100))
        self.assertIn('width:200%', page_image_html(image,200))
        self.assertIn('max-width:none!important', page_image_html(image,200))

    def test_plain_text_is_escaped_and_uses_theme(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test.txt'
            path.write_text('<script>alert(1)</script>', encoding='utf-8')
            with patch('document_viewer.st.html') as html:
                render_document(path, folder)
                output = html.call_args.args[0]
                self.assertIn('&lt;script&gt;',output)
                self.assertIn('background:var(--panel)',output)
                self.assertNotIn('<script>',output)

    def test_cache_changes_with_file_content_and_does_not_modify_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'document.docx'
            source.write_bytes(b'first version')
            engine = root/'soffice'
            engine.write_bytes(b'test binary marker')
            def fake_converter(command,**kwargs):
                destination = Path(command[command.index('--outdir')+1])/'source.pdf'
                writer = PdfWriter()
                writer.add_blank_page(width=300,height=400)
                writer.write(destination)
                class Result:
                    returncode = 0
                return Result()
            with patch('document_viewer.find_office',return_value=str(engine)), patch('document_viewer.subprocess.run',side_effect=fake_converter) as run:
                first = convert(source,root/'cache')
                self.assertEqual(convert(source,root/'cache'),first)
                self.assertEqual(run.call_count,1)
                self.assertEqual(source.read_bytes(),b'first version')
                source.write_bytes(b'second version')
                second = convert(source,root/'cache')
                self.assertNotEqual(first,second)
                self.assertTrue(first.exists())
                self.assertTrue(second.exists())

    def test_missing_converter_is_explicit(self):
        with patch('document_viewer.find_office',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'LibreOffice'):
                convert('missing.docx','unused')

"""Describe extraction coverage without claiming the source itself is complete."""
import re
from pathlib import Path


def inspect_coverage(path, sections, expected_pages=None):
    path = Path(path)
    report = {'source_pages':None, 'text_pages':None, 'expected_pages':expected_pages,
              'section_count':len(sections), 'warnings':[], 'completeness':'unverified'}
    if path.suffix.lower() == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            reader.decrypt('')
        report['source_pages'] = len(reader.pages)
        covered = {int(m.group(1)) for label, _ in sections
                   if (m := re.fullmatch(r'(\d+)-р хуудас', label))}
        report['text_pages'] = len(covered)
        if len(covered) < len(reader.pages):
            report['warnings'].append('Зарим хуудсанд текст задраагүй. Скан, зураг эсвэл хоосон хуудас байж болно.')
        if expected_pages and expected_pages != len(reader.pages):
            report['warnings'].append('Эх файлын хуудасны тоо таны заасан тоотой таарахгүй байна.')
        text = ' '.join(value for _, value in sections).casefold()
        if len(reader.pages) == 1 and ('хавсралт' in text or 'appendix' in text or 'annex' in text):
            report['warnings'].append('Нэг хуудаст эх файл хавсралт дурдсан байна. Хавсралт хамт байгаа эсэхийг шалгана уу; энэ нь автоматаар батлагдаагүй.')
    report['warnings'].append('Текст задарсан нь эх баримтын бүх хавсралт, заалт байгаа гэсэн баталгаа биш.')
    return report

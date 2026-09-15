"""Evaluate retrieval against a disposable restored snapshot, never live data/API."""
import argparse
import json
import tempfile
import time
from pathlib import Path
from contextlib import closing
from database import open_database, init_db
from preserve_data import restore_to_empty
from rag_service import DocumentRAG

CASES = [
    ('Ээлжийн амралтын журмыг хэдэн оноос мөрдөх вэ?', 'амралт'),
    ('Ээлжийн амралт олгох журам 2022 оноос мөрдөх үү?', 'амралт'),
    ('Албан томилолтын хоолны зардлыг хэн тогтоох вэ?', 'ТОМИЛОЛТ'),
    ('Хөдөлмөрийн аюулгүй ажиллагааны зааварчилгаа', 'АЮУЛГҮЙ'),
    ('Гэрч хохирогчийн мэдээллийн нууцлалын гэрээ', 'ГЭРЧ'),
    ('Монгол улсын иргэнд газар өмчлүүлэх тухай', 'ГАЗАР'),
    ('Дадлагажигч их эмчийн ажиллах журам', 'ДАДЛАГАЖИГЧ'),
    ('Төрийн албан хаагчийн мөнгөн урамшуулал', 'УРАМШУУЛАЛ'),
    ('Сахилгын шийтгэлд гомдол гаргах журам', 'сахилгын'),
    ('Хөрөнгө оруулалтын тухай хууль', 'Хөрөнгө'),
    ('When does the leave regulation start?', 'амралт'),
    ('Tell me about land ownership', 'ГАЗАР'),
    ('Travel expense policy', 'ТОМИЛОЛТ'),
    ('Witness confidentiality contract', 'ГЭРЧ'),
    ('Workplace safety instructions', 'АЮУЛГҮЙ'),
    ('Кванткомпьютерийн кубитын давтамж хэд вэ?', None),
    ('What is the weather on Mars?', None),
]


def evaluate(archive):
    with tempfile.TemporaryDirectory() as temporary:
        root = restore_to_empty(archive,Path(temporary)/'data')
        init_db(root/'dms_system.db')
        with closing(open_database(root/'dms_system.db')) as conn:
            records = [dict(zip(('id','title','file_path','file_type'),row)) for row in
                       conn.execute("SELECT id,title,file_path,file_type FROM documents WHERE status='active'")]
        started = time.perf_counter()
        index = DocumentRAG(records,root)
        elapsed = time.perf_counter()-started
        results = []
        for question, expected in CASES:
            started = time.perf_counter()
            sources = index.retrieve(question,limit=5)
            passed = not sources if expected is None else any(expected.casefold() in s.title.casefold() for s in sources)
            results.append({'question':question,'passed':passed,'seconds':round(time.perf_counter()-started,4),
                            'titles':[s.title for s in sources]})
        return {'passed':sum(r['passed'] for r in results),'total':len(results),
                'index_seconds':round(elapsed,3),'results':results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('archive')
    args = parser.parse_args()
    result = evaluate(args.archive)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['passed'] == result['total'] else 1)

import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import database
import chat_requests as jobs


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)/'test.db'
        database.init_db(self.path)
        with closing(database.open_database(self.path)) as c, c:
            c.execute("INSERT INTO chat_sessions(id,user_id,title) VALUES (1,1,'Шинэ чат')")
        jobs.ensure_schema(self.path)

    def test_save_before_call_and_idempotent_finish(self):
        self.assertTrue(jobs.begin(self.path,'a',1,1,'Question'))
        with closing(database.open_database(self.path)) as c:
            self.assertEqual(c.execute('SELECT content FROM chat_messages').fetchall(), [('Question',)])
        self.assertFalse(jobs.begin(self.path,'a',1,1,'Question'))
        self.assertTrue(jobs.finish(self.path,'a',1,'Answer'))
        self.assertFalse(jobs.finish(self.path,'a',1,'Duplicate'))

    def test_concurrent_single_flight(self):
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda key: jobs.begin(self.path,key,1,1,'Question'), ['a','b']))
        self.assertEqual(sum(results),1)

    def test_interruption_and_late_result(self):
        jobs.begin(self.path,'a',1,1,'Keep me')
        self.assertTrue(jobs.recover(self.path,1,1))
        with closing(database.open_database(self.path)) as c, c:
            c.execute("UPDATE chat_jobs SET created_at=datetime('now','-11 minutes')")
        self.assertFalse(jobs.recover(self.path,1,1))
        self.assertFalse(jobs.finish(self.path,'a',1,'Late answer'))
        with closing(database.open_database(self.path)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM chat_messages').fetchone()[0],2)
        self.assertFalse(jobs.recover(self.path,1,1))

    def test_wrong_owner(self):
        with self.assertRaises(PermissionError):
            jobs.begin(self.path,'a',1,999,'Forbidden')
        jobs.begin(self.path,'a',1,1,'Question')
        self.assertFalse(jobs.finish(self.path,'a',999,'Forbidden'))

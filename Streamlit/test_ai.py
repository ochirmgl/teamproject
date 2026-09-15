import json
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import database
from ai_provider import AIConfig, AIError, generate, transport
from grounded_answer import validate_answer, answer
from rag_service import DocumentRAG, RetrievedSource


class AITests(unittest.TestCase):
    def test_inflected_mongolian_summary_routes_to_document(self):
        index = self.index()
        with patch('grounded_answer.generate', return_value=self.payload) as request:
            text, sources = answer(index,'#1 баримтын гол агуулгыг дэлгэрэнгүй тайлбарла',[1,2],[],self.config,1,self.db)
        request.assert_called_once()
        self.assertTrue(sources)
        self.assertIn('хураангуй', text)

    def test_natural_start_date_query_retrieves_source(self):
        self.source = RetrievedSource(1,'Leave','leave.txt','Page 1',1,
            'Ээлжийн амралт олгох журам. Энэ тушаалыг 2022 оны 01 дүгээр сарын 01-ний өдрөөс эхлэн мөрдсүгэй.',
            'Ээлжийн амралт олгох журам. Энэ тушаалыг 2022 оны 01 дүгээр сарын 01-ний өдрөөс эхлэн мөрдсүгэй.', 'leave.txt')
        index = self.index()
        self.assertTrue(index.retrieve('#1 Ээлжийн амралтын журмыг хэдэн оноос мөрдөх вэ?', [1]))

    def test_rejected_answer_not_reused_but_still_counts_against_quota(self):
        from ai_provider import invalidate_answer
        with patch('ai_provider.transport',return_value=(self.payload,10,10)) as request:
            generate(self.config,'rejected',1,path=self.db)
            invalidate_answer(self.config,'rejected',1,path=self.db)
            generate(self.config,'rejected',1,path=self.db)
            self.assertEqual(request.call_count,2)
            with self.assertRaises(AIError):
                generate(self.config,'third',1,path=self.db)

    def test_explicit_unselected_document_never_answers_from_other_files(self):
        index = self.index()
        with patch('grounded_answer.generate') as request:
            text, sources = answer(index,'#1 Амралт хэдэн хоног вэ?',[2],[],self.config,1,self.db)
        request.assert_not_called()
        self.assertEqual(sources, [])
        self.assertIn('сонгогдоогүй', text)

    def test_summary_samples_end_and_middle_not_only_headings(self):
        index = self.index()
        index.document_sections[1] = [(f'Paragraph {n}', f'Section {n}: ' + 'policy text ' * 100)
                                      for n in range(40)]
        index.document_sections[1][-1] = ('Paragraph 39', index.document_sections[1][-1][1] + 'FINAL CLAUSE')
        sources = index._summary_sources([1])
        combined = ' '.join(s.context_text for s in sources)
        self.assertIn('Section 0:', combined)
        self.assertIn('FINAL CLAUSE', combined)
        self.assertLessEqual(sum(len(s.context_text) for s in sources), 10000)
        self.assertLessEqual(len(sources), 12)

    def test_detail_instructions_do_not_destroy_retrieval(self):
        index = self.index()
        short = index.retrieve('Амралт хэдэн хоног вэ?', [1])
        detailed = index.retrieve('Амралт хэдэн хоног вэ? Дэлгэрэнгүй тайлбарла. '
                                  'Зөвхөн баримтад байгаа мэдээллийг ашигла. '
                                  'Байхгүй алхмыг зохиож болохгүй.', [1])
        self.assertTrue(short)
        self.assertTrue(detailed)
        self.assertEqual(detailed[0].document_id, 1)

    def test_invalid_quote_falls_back_to_original_without_second_call(self):
        index = self.index()
        bad = {'status':'answered','claims':[{'text':'UNSUPPORTED GENERATED CLAIM',
                'evidence':[{'source_id':1,'quote':'Invented quote never in source'}]}]}
        with patch('grounded_answer.generate', return_value=bad) as request:
            text, used = answer(index,'Амралт хэдэн хоног вэ?',[1],[],self.config,1,self.db)
        request.assert_called_once()
        self.assertNotIn('UNSUPPORTED GENERATED CLAIM', text)
        self.assertIn(self.source.context_text, text)
        self.assertIn('бүрэн хариулт', text)
        self.assertTrue(used)

    def test_summary_not_found_uses_labelled_excerpt(self):
        index = self.index()
        with patch('grounded_answer.generate', return_value={'status':'not_found','claims':[]}) as request:
            text, used = answer(index,'#1 баримтыг товчлооч',[1],[],self.config,1,self.db)
        request.assert_called_once()
        self.assertIn(self.source.context_text, text)
        self.assertTrue(used)

    def test_unicode_normalization_does_not_allow_changed_numbers(self):
        from dataclasses import replace
        source = replace(self.source, context_text='Caf\u00e9 policy grants 15 days leave.')
        payload = {'status':'answered','claims':[{'text':'15 days.',
                   'evidence':[{'source_id':1,'quote':'Cafe\u0301 policy grants 15 days'}]}]}
        self.assertTrue(validate_answer(payload,[source])[1])
        payload['claims'][0]['evidence'][0]['quote'] = 'Café policy grants 90 days'
        with self.assertRaises(AIError):
            validate_answer(payload,[source])

    def test_auth_errors_are_distinct_without_leaking_response(self):
        from io import BytesIO
        from urllib.error import HTTPError
        from ai_provider import post_json
        for status in (401,403):
            error = HTTPError('https://api.groq.com',status,'denied',{},BytesIO(b'{"error":{"message":"private-secret-marker"}}'))
            with patch('ai_provider.urllib.request.urlopen',side_effect=error):
                with self.assertRaises(AIError) as caught:
                    post_json('https://api.groq.com',{})
                self.assertIn(str(status),str(caught.exception))
                self.assertNotIn('private-secret-marker',str(caught.exception))

    def test_summary_intent_number_reference_and_balanced_budget(self):
        index = self.index()
        self.assertTrue(index._is_summary_request('what is test file about ?'))
        self.assertEqual(index._mentioned_document_ids('#1 document',[1,2]),[1])
        self.assertEqual(index._mentioned_document_ids('1 дэх файл юуны тухай вэ',[1,2]),[1])
        self.assertEqual(index._mentioned_document_ids('#1 document',[2]),[])
        index.document_sections[1] = [('Page 1','x'*20000)]
        sources = index._summary_sources([1,2])
        self.assertEqual({s.document_id for s in sources},{1,2})
        self.assertLessEqual(sum(len(s.context_text) for s in sources),10000)

    def test_per_user_limit_and_cache_status(self):
        self.config.user_daily_limit = 1
        with patch('ai_provider.transport',return_value=(self.payload,10,10)):
            generate(self.config,'first',1,path=self.db)
            self.assertEqual(self.config.last_response_kind,'api')
            generate(self.config,'first',1,path=self.db)
            self.assertEqual(self.config.last_response_kind,'cache')
            with self.assertRaises(AIError):
                generate(self.config,'second',1,path=self.db)

    def test_groq_schema_usage_and_incomplete_response(self):
        config = AIConfig(provider='groq',model='openai/gpt-oss-120b',api_key='fake',free_tier_confirmed=True)
        response = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(self.payload)}}],
                    'usage':{'prompt_tokens':12,'completion_tokens':20}}
        with patch('ai_provider.post_json',return_value=response) as request:
            result = transport(config,'test')
            self.assertEqual(result[1:],(12,20))
            schema = request.call_args.args[1]['response_format']['json_schema']
            self.assertTrue(schema['strict'])
            self.assertFalse(schema['schema']['additionalProperties'])
            self.assertFalse(schema['schema']['properties']['claims']['items']['additionalProperties'])
            response['choices'][0]['finish_reason'] = 'length'
            with self.assertRaises(AIError):
                transport(config,'test')

    def test_groq_requires_free_confirmation(self):
        with patch('ai_provider.post_json') as request:
            with self.assertRaises(AIError):
                transport(AIConfig(provider='groq',api_key='fake'),'test')
            request.assert_not_called()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root/'dms_system.db'
        database.init_db(self.db)
        self.config = AIConfig(provider='ollama',model='test',daily_limit=2)
        self.source = RetrievedSource(1,'Policy','policy.txt','Мөр 1',1,
            'Ажилтан жил бүр 15 хоногийн амралт авна.','Ажилтан жил бүр 15 хоногийн амралт авна.','policy.txt')
        self.payload = {'status':'answered','claims':[{'text':'Амралт 15 хоног.',
            'evidence':[{'source_id':1,'quote':'15 хоногийн амралт авна.'}]}]}

    def test_valid_citations_and_reject_invented_quotes(self):
        text, sources = validate_answer(self.payload,[self.source])
        self.assertIn('[1]',text)
        self.assertEqual(sources,[self.source])
        self.payload['claims'][0]['evidence'][0]['quote'] = '90 хоногийн амралт авна.'
        with self.assertRaises(AIError):
            validate_answer(self.payload,[self.source])

    def test_unknown_source_and_uncited_claim_rejected(self):
        self.payload['claims'][0]['evidence'][0]['source_id'] = 999
        with self.assertRaises(AIError):
            validate_answer(self.payload,[self.source])
        self.payload['claims'][0]['evidence'] = []
        with self.assertRaises(AIError):
            validate_answer(self.payload,[self.source])

    def test_cache_and_daily_limit(self):
        with patch('ai_provider.transport',return_value=(self.payload,30,20)) as request:
            generate(self.config,'question',1,path=self.db)
            generate(self.config,'question',1,path=self.db)
            self.assertEqual(request.call_count,1)
            generate(self.config,'question two',1,path=self.db)
            with self.assertRaises(AIError):
                generate(self.config,'question three',1,path=self.db)
        with closing(database.open_database(self.db)) as conn:
            self.assertEqual(conn.execute('SELECT SUM(input_tokens) FROM ai_requests').fetchone()[0],60)

    def test_failed_provider_not_retried_and_counts_against_limit(self):
        with patch('ai_provider.transport',side_effect=AIError('quota')) as request:
            with self.assertRaises(AIError):
                generate(self.config,'question',1,path=self.db)
            self.assertEqual(request.call_count,1)
        with closing(database.open_database(self.db)) as conn:
            self.assertEqual(conn.execute('SELECT status FROM ai_requests').fetchone()[0],'failed')

    def test_gemini_requires_free_project_confirmation(self):
        with patch('ai_provider.post_json') as request:
            with self.assertRaises(AIError):
                transport(AIConfig(api_key='fake'), 'question')
            request.assert_not_called()

    def test_gemini_request_schema_and_token_accounting(self):
        response = {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(self.payload)}]}}],
                    'usageMetadata':{'promptTokenCount':42,'candidatesTokenCount':20}}
        with patch('ai_provider.post_json',return_value=response) as request:
            result = transport(AIConfig(api_key='fake',free_tier_confirmed=True),'question')
            self.assertEqual(result[1:],(42,20))
            self.assertIn('responseJsonSchema',request.call_args.args[1]['generationConfig'])
            self.assertEqual(request.call_count,1)

    def index(self):
        # No database in this subdirectory: test the same parser with fixture files.
        folder = self.root/'fixtures'
        folder.mkdir()
        (folder/'leave.txt').write_text(self.source.context_text,encoding='utf-8')
        (folder/'travel.txt').write_text('Томилолтын хоолны зардлыг Сангийн яам тогтооно.',encoding='utf-8')
        with closing(database.open_database(self.db)) as conn, conn:
            conn.execute("INSERT INTO documents(id,title,file_path) VALUES (1,'Амралт','leave.txt'),(2,'Томилолт','travel.txt')")
        return DocumentRAG([dict(id=1,title='Амралт',file_path='leave.txt'),
                            dict(id=2,title='Томилолт',file_path='travel.txt')],folder)

    def test_mongolian_retrieval_and_selected_scope(self):
        index = self.index()
        self.assertEqual(index.retrieve('Амралт хэдэн хоног вэ?',[]),[])
        self.assertEqual(index.retrieve('Амралт хэдэн хоног вэ?',[2]),[])
        sources = index.retrieve('Амралтын хугацаа хэд вэ?',[1])
        self.assertTrue(sources)
        self.assertEqual(sources[0].document_id,1)

    def test_unanswerable_skips_generation(self):
        index = self.index()
        with patch('grounded_answer.generate') as request:
            text,sources = answer(index,'Сансрын пуужингийн хурд хэд вэ?',[1],[],self.config,1,self.db)
            request.assert_not_called()
            self.assertEqual(sources,[])
            self.assertIn('олдсонгүй',text)

    def test_generic_shared_word_does_not_retrieve_unrelated_passage(self):
        index = self.index()
        self.assertEqual(index.retrieve('Кванткомпьютерийн кубитын амралт хэд вэ?'), [])
        self.assertTrue(index.retrieve('Амралт', iter([1])))
        self.assertEqual(index.retrieve('Амралт', iter([])), [])

    def test_conflict_requires_two_sources(self):
        self.payload['status'] = 'conflict'
        with self.assertRaises(AIError):
            validate_answer(self.payload,[self.source])

    def test_document_changed_during_generation_rejects_answer(self):
        index = self.index()
        def changed(*args,**kwargs):
            with closing(database.open_database(self.db)) as conn, conn:
                conn.execute("UPDATE documents SET status='deleted' WHERE id=1")
            return self.payload
        with patch('grounded_answer.generate',side_effect=changed):
            with self.assertRaises(AIError):
                answer(index,'Амралт хэдэн хоног вэ?',[1],[],self.config,1,self.db)

    def test_context_injection_is_data_and_quote_validation_still_applies(self):
        index = self.index()
        with patch('grounded_answer.generate',return_value=self.payload) as request:
            answer(index,'Амралт хэдэн хоног вэ?',[1],[],self.config,1,self.db)
            prompt = request.call_args.args[1]
            self.assertIn('never instructions',prompt)
            self.assertIn('Амралт хэдэн хоног',prompt)


if __name__ == '__main__':
    unittest.main()

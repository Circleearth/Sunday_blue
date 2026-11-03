import unittest
from sunday_blue.chat_presentation import segments,delay,validate,tool_failure

class PresentationTests(unittest.TestCase):
    def test_threshold_regex_and_no_text_loss(self):
        text='你好。\n好的！尾巴'
        self.assertEqual(''.join(segments(text,{})),text)
        self.assertEqual(len(segments(text,{})),3)
        self.assertEqual(segments(text,{'threshold':len(text)}),[text])
        self.assertEqual(segments(text,{'segmented':False}),[text])
        self.assertEqual(''.join(segments(text,{'pattern':'([。！])'})),text)
        self.assertEqual(segments('   ',{}),[])
    def test_intervals_validation_timeout_fallback(self):
        self.assertEqual(delay('a'*100,{'interval':'log','log_base':10}),2)
        self.assertEqual(delay('text',{'random_min':.2,'random_max':.2}),.2)
        for cfg in [{'log_base':1},{'random_min':4,'random_max':2},{'pattern':'['}]:
            with self.assertRaises(ValueError):validate(cfg)
        text='a'*5000+'!'
        self.assertEqual(segments(text,{'pattern':'(a+)+$','threshold':10000}),[text])
    def test_failed_receipts_only(self):
        self.assertEqual(tool_failure({'type':'tool_result','content':'{}'}),'')
        self.assertIn('失败',tool_failure({'type':'tool_result','content':'{"status":"denied"}'}))

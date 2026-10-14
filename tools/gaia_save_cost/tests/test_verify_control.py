import importlib.util,tempfile,unittest,xml.etree.ElementTree as ET
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('control',HERE/'verify_control.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
SOURCE=HERE.parents[1]/'Content.IntegrationTests/GaiaSaveCostHostTests.cs'
class ControlParserTests(unittest.TestCase):
    def classify(self,case,wrong_line=False,partial=True):
        with tempfile.TemporaryDirectory() as raw:
            folder=Path(raw);trx=folder/'run.trx';log=folder/'run.log'
            root=ET.Element('TestRun')
            positive=case in ['close','yield','reader-rejection']
            name=control.TEST if case!='reader-rejection' else 'Content.IntegrationTests.GaiaSaveCostReaderControlTests.RejectWrongShardPayload'
            result=ET.SubElement(root,'UnitTestResult',testName=name,outcome='Passed' if positive else 'Failed')
            if not positive:
                number=next(i+1 for i,line in enumerate(SOURCE.read_text().splitlines()) if control.NEEDLES[case] in line)
                ET.SubElement(result,'StackTrace').text='GaiaSaveCostHostTests.cs:line '+str(number+int(wrong_line))
            ET.ElementTree(root).write(trx)
            log.write_text('GAIA_CONTROL_CASE:'+case+'\n'+('GAIA_READER_REJECTION_COMPLETE' if case=='reader-rejection' else 'GAIA_SAVE_STOPPED_AUDIT ' if positive else 'GAIA_SAVE_PARTIAL ' if partial else ''))
            return control.verify(case,SOURCE,trx,log)
    def test_expected_assertions(self):
        for case in control.NEEDLES:
            with self.subTest(case=case):self.assertTrue(self.classify(case)['native_control_result_classified'])
    def test_wrong_assertions_rejected(self):
        for case in control.NEEDLES:
            with self.subTest(case=case),self.assertRaises(AssertionError):self.classify(case,wrong_line=True)
    def test_missing_partial_rejected(self):
        with self.assertRaises(AssertionError):self.classify('cap',partial=False)
    def test_positive_and_reader(self):
        for case in ['close','yield','reader-rejection']:
            with self.subTest(case=case):self.assertTrue(self.classify(case)['native_control_result_classified'])
if __name__=='__main__':unittest.main()

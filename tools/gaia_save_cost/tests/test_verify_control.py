import importlib.util,json,tempfile,unittest,xml.etree.ElementTree as ET
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('control',HERE/'verify_control.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
SOURCE=HERE.parents[1]/'Content.IntegrationTests/GaiaSaveCostHostTests.cs'
class ControlParserTests(unittest.TestCase):
    def classify(self,case,wrong_line=False,partial=True,elapsed=10,postseal=True):
        with tempfile.TemporaryDirectory() as raw:
            folder=Path(raw);trx=folder/'run.trx';log=folder/'run.log'
            root=ET.Element('TestRun')
            positive=case in ['close','yield','reader-rejection']
            name=control.TEST if case!='reader-rejection' else 'Content.IntegrationTests.GaiaSaveCostReaderControlTests.RejectWrongShardPayload'
            result=ET.SubElement(root,'UnitTestResult',testId='fixture-id',testName=name.rsplit('.',1)[1],outcome='Passed' if positive else 'Failed')
            definition=ET.SubElement(root,'UnitTest',id='fixture-id')
            cls,method=name.rsplit('.',1)
            ET.SubElement(definition,'TestMethod',className=cls,name=method,adapterTypeName='executor://nunit3testexecutor/')
            if not positive:
                number=next(i+1 for i,line in enumerate(SOURCE.read_text().splitlines()) if control.NEEDLES[case] in line)
                ET.SubElement(result,'StackTrace').text='GaiaSaveCostHostTests.cs:line '+str(number+int(wrong_line))
            ET.ElementTree(root).write(trx)
            log.write_text('GAIA_CONTROL_CASE:'+case+'\n'+('GAIA_READER_REJECTION_COMPLETE' if case=='reader-rejection' else 'GAIA_SAVE_STOPPED_AUDIT '+json.dumps(dict(postSealNaturalTicks=10,postSealElapsedDeciseconds=elapsed)) if positive else 'GAIA_SAVE_PARTIAL ' if partial else ''))
            if case=='late-write' and postseal:
                with log.open('a') as out:out.write('\nGAIA_CONTROL_POST_SEAL_WRITE')
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
    def test_short_postseal_observation_rejected(self):
        with self.assertRaises(AssertionError):self.classify('close',elapsed=2)
    def test_missing_postseal_write_rejected(self):
        with self.assertRaises(AssertionError):self.classify('late-write',postseal=False)

class TrxIdentityTests(unittest.TestCase):
    def check(self,mutation=None):
        with tempfile.TemporaryDirectory() as raw:
            root=ET.Element('TestRun',xmlns='http://microsoft.com/schemas/VisualStudio/TeamTest/2010')
            result=ET.SubElement(root,'UnitTestResult',testId='actual-id',testName='FullGaiaSaveWindow',outcome='Passed')
            definition=ET.SubElement(root,'UnitTest',id='actual-id')
            method=ET.SubElement(definition,'TestMethod',className='Content.IntegrationTests.GaiaSaveCostHostTests',
                name='FullGaiaSaveWindow',adapterTypeName='executor://nunit3testexecutor/')
            if mutation:mutation(root,result,definition,method)
            path=Path(raw)/'actual.trx';ET.ElementTree(root).write(path)
            return control.result_for_test(path,control.TEST)
    def test_real_trx_shape(self):self.assertEqual(self.check().attrib['outcome'],'Passed')
    def test_other_class_rejected(self):
        with self.assertRaises(AssertionError):self.check(lambda root,result,definition,method:method.set('className','OtherClass'))
    def test_wrong_definition_id_rejected(self):
        with self.assertRaises(AssertionError):self.check(lambda root,result,definition,method:definition.set('id','other-id'))
    def test_missing_definition_rejected(self):
        with self.assertRaises(AssertionError):self.check(lambda root,result,definition,method:root.remove(definition))
    def test_wrong_result_name_rejected(self):
        with self.assertRaises(AssertionError):self.check(lambda root,result,definition,method:result.set('testName','OtherMethod'))
    def test_extra_result_rejected(self):
        with self.assertRaises(AssertionError):self.check(lambda root,*_:ET.SubElement(root,'UnitTestResult'))
if __name__=='__main__':unittest.main()

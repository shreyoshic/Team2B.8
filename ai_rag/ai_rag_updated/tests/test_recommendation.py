import unittest
from ai_rag import recommend_resolution


def fixture(value, unit='°C', date=None, entity='MX-01', ref='report.pdf#page=1'):
    text = f'Machine ID: {entity}\nObserved temperature: {value}{unit}'
    if date:
        text += '\nDate: ' + date
    c = dict(entity=entity, claim='temperature', value=value, unit=unit, source_reference=ref)
    if date:
        c['timestamp_text'] = date
    return c, dict(text=text, document=ref.split('#')[0], page=1, source_reference=ref)


class RecommendationTests(unittest.TestCase):
    def check(self, left, right):
        return recommend_resolution([left[0], right[0]], [left[1], right[1]])

    def test_conflict_stays_unresolved(self):
        r = self.check(fixture(72), fixture(91, ref='log.pdf#page=1'))
        self.assertEqual(r['status'], 'UNRESOLVED')
        self.assertIsNone(r['recommended_value'])
        self.assertEqual([c['value'] for c in r['original_claims']], [72, 91])

    def test_match(self):
        self.assertEqual(self.check(fixture(72), fixture(72))['status'], 'AGREEMENT')

    def test_units_normalize_without_replacing(self):
        r = self.check(fixture(0), fixture(32, '°F'))
        self.assertEqual(r['status'], 'AGREEMENT')
        self.assertEqual(r['original_claims'][1]['value'], 32)
        self.assertEqual(r['original_claims'][1]['unit'], '°F')

    def test_different_dates_retained(self):
        self.assertEqual(self.check(fixture(72, date='2026-10-03'), fixture(91, date='2026-10-04'))['status'], 'CONTEXTUALIZED')

    def test_missing_evidence(self):
        r = recommend_resolution([fixture(72)[0], fixture(91)[0]], [])
        self.assertEqual(r['supporting_evidence'], [])
        self.assertEqual(r['status'], 'UNRESOLVED')

    def test_fabricated_citation(self):
        c,p=fixture(72)
        c['source_reference']='invented.pdf#page=1'
        self.assertEqual(recommend_resolution([c],[p])['supporting_evidence'], [])

    def test_unsubstantiated_value(self):
        c,p=fixture(72)
        c['value']=91
        self.assertEqual(recommend_resolution([c],[p])['supporting_evidence'], [])

    def test_different_machine(self):
        self.assertEqual(self.check(fixture(72), fixture(91, entity='MX-02'))['status'], 'CONTEXTUALIZED')

    def test_date_not_in_passage_is_ignored(self):
        a,b=fixture(72),fixture(91)
        a[0]['timestamp_text']='2026-10-03'
        b[0]['timestamp_text']='2026-10-04'
        self.assertEqual(self.check(a,b)['status'],'UNRESOLVED')

"""Evidence-grounded recommendations for P2; no server and no invented citations."""
from copy import deepcopy
from datetime import datetime
import math
import re


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _normalize(value, unit):
    if unit == '°C':
        return value, '°C'
    if unit == '°F':
        return (value - 32) * 5 / 9, '°C'
    return value, unit


def recommend_resolution(claims, passages, question=None):
    """Receive claims plus passages from retrieval/verification; return JSON dict.

    Numeric scalar measurements are supported. Range/maximum claims are context,
    never substitutes for measurements. Citation consistency is checked against
    the supplied passage, not against original source authenticity.
    """
    if not isinstance(claims, list) or not isinstance(passages, list):
        raise ValueError('claims and passages must be arrays')
    if not all(isinstance(c, dict) for c in claims + passages):
        raise ValueError('claims and passages must contain objects')
    original = deepcopy(claims)
    result = {
        'status': 'UNRESOLVED', 'recommendation': 'Keep the original values and request additional evidence.',
        'recommended_value': None, 'original_claims': original,
        'supporting_evidence': [], 'reasoning': [], 'comparisons': [],
        'uncertainty': {'level': 'high', 'limitations': []},
        'next_steps': [], 'question': question,
    }
    accepted, rejected, seen = [], [], set()
    for index, claim in enumerate(claims):
        value = _number(claim.get('value'))
        if claim.get('claim_kind', 'measurement') != 'measurement':
            continue
        if value is None or not all(isinstance(claim.get(k), str) and claim[k].strip() for k in ('entity', 'claim', 'unit', 'source_reference')):
            rejected.append(index)
            continue
        ref = claim['source_reference']
        candidates = [p for p in passages if p.get('source_reference') == ref
                      and (not claim.get('chunk_id') or p.get('chunk_id') == claim['chunk_id'])
                      and (not claim.get('source_hash') or p.get('source_hash') == claim['source_hash'])]
        passage = None
        for p in candidates:
            text = p.get('text', '')
            if not isinstance(text, str):
                continue
            # Entity and attribute must be explicitly present in this passage.
            if claim['entity'].lower() not in text.lower() or claim['claim'].lower() not in text.lower():
                continue
            found = re.findall(r'(?<![\d.])(-?\d+(?:\.\d+)?)\s*(°[CF])\b', text, re.I)
            if not any(float(v) == value and u.upper() == claim['unit'].upper() for v, u in found):
                continue
            passage = p
            break
        if passage is None:
            rejected.append(index)
            continue
        normalized, canonical_unit = _normalize(value, claim['unit'])
        timestamp = claim.get('timestamp_text')
        # Dates are compared only if visible in the passage and parseable.
        parsed_date = None
        if isinstance(timestamp, str) and timestamp in passage['text']:
            for fmt in ('%d %B %Y', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S%z'):
                try:
                    parsed_date = datetime.strptime(timestamp, fmt).isoformat()
                    break
                except ValueError:
                    pass
        accepted.append((index, claim, normalized, canonical_unit, parsed_date))
        key = (ref, passage.get('chunk_id'), passage['text'])
        if key not in seen:
            result['supporting_evidence'].append(deepcopy(passage))
            seen.add(key)
    if rejected:
        result['uncertainty']['limitations'].append(f'Claims at positions {rejected} lack valid matching source passages or supported scalar values.')
    if len(accepted) < 2:
        result['reasoning'].append('Fewer than two supported measurements are available for comparison.')
        result['next_steps'].append('Provide the original passages containing each measurement, entity, unit and source reference.')
        return result
    outcomes = []
    for offset, left in enumerate(accepted):
        for right in accepted[offset + 1:]:
            i, a, av, au, adate = left
            j, b, bv, bu, bdate = right
            comparison = {'claim_indices': [i, j], 'source_references': [a['source_reference'], b['source_reference']],
                          'normalized_values': [av, bv], 'comparison_unit': au,
                          'dates': [adate, bdate]}
            if (a['entity'], a['claim']) != (b['entity'], b['claim']):
                outcome, reason = 'DIFFERENT_CONTEXT', 'The measurements describe different entities or attributes.'
            elif au != bu:
                outcome, reason = 'INCOMPARABLE', 'The units cannot be compared by this module.'
            elif math.isclose(av, bv, rel_tol=0, abs_tol=1e-6):
                outcome, reason = 'MATCH', 'The values agree after explicit unit normalization.'
            elif adate and bdate and adate != bdate:
                outcome, reason = 'DIFFERENT_DATES', 'The readings have different recorded dates; both may be valid observations.'
            else:
                outcome, reason = 'CONFLICT', 'The supported values differ, and available dates/context do not explain the difference.'
            comparison.update(outcome=outcome, reasoning=reason)
            outcomes.append(outcome)
            result['comparisons'].append(comparison)
    result['reasoning'] = list(dict.fromkeys(c['reasoning'] for c in result['comparisons']))
    result['reasoning'].append('Source relevance identifies evidence about the same machine and attribute; it does not establish which source is correct.')
    if not rejected and all(o == 'MATCH' for o in outcomes):
        result.update(status='AGREEMENT', recommendation='Report the agreement, retaining each original value and source.',
                      recommended_value={'value': accepted[0][2], 'unit': accepted[0][3]})
        result['uncertainty'] = {'level': 'low', 'limitations': ['Agreement does not independently prove accuracy or source authenticity.']}
    elif not rejected and not any(o in ('CONFLICT', 'INCOMPARABLE') for o in outcomes):
        result.update(status='CONTEXTUALIZED', recommendation='Retain the readings separately with their entities, attributes and recorded dates; do not merge them into one value.')
        result['uncertainty'] = {'level': 'medium', 'limitations': ['Distinct contexts explain why values need not match, but do not establish a current or correct value.']}
    else:
        result['recommendation'] = 'Keep both original readings, flag the discrepancy for review, and do not choose a value automatically.'
        result['uncertainty']['limitations'].append('Source authority, measurement conditions, timestamps or instrument calibration are insufficient to select a correct reading.')
        result['next_steps'] = ['Check measurement timestamps and operating conditions.', 'Confirm sensor calibration and obtain a repeat measurement or a dated authoritative record.']
    return result

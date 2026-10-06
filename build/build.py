"""Build index.html from the single source of truth.

    data/questions.csv  one row per question (edit this)
    data/meta.json      sections, sources, resume triggers, playbooks, page text
    src/template.html   page layout, with placeholders for the data

Everything else (section, section_title, hot_score, score_factors, the hot list,
section counts, gap drills, resume trigger question lists, company coverage and
source back-links) is recomputed here, so it can never drift from the questions.

Usage:
    python build/build.py          validate and write index.html
    python build/build.py --check  validate and fail if index.html is out of date
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_CSV = ROOT / 'data' / 'questions.csv'
META_JSON = ROOT / 'data' / 'meta.json'
TEMPLATE_HTML = ROOT / 'src' / 'template.html'
OUTPUT_HTML = ROOT / 'index.html'

DATA_PLACEHOLDER = '{{HANDBOOK_DATA}}'
SECTIONS_PLACEHOLDER = '{{SECTION_COUNT}}'

# CSV columns in the order they appear in the spreadsheet.
COLUMNS = ['id', 'topic', 'question', 'answer', 'level', 'level_basis', 'round', 'evidence',
           'frequency', 'harsh_status', 'resume_hooks', 'company_types', 'companies', 'keywords',
           'followups', 'trap', 'verify', 'notes', 'code', 'fs_link']
LIST_COLUMNS = {'resume_hooks', 'company_types', 'keywords', 'verify'}  # "a | b | c"
JSON_COLUMNS = {'companies', 'followups', 'code'}                       # JSON text
REQUIRED_COLUMNS = {'id', 'topic', 'question', 'answer', 'level', 'level_basis', 'round',
                    'evidence', 'frequency', 'harsh_status', 'trap'}
LIST_SEPARATOR = ' | '

# Key order of each question in the generated page.
QUESTION_KEYS = ['id', 'topic', 'question', 'level', 'level_basis', 'round', 'evidence', 'frequency',
                 'companies', 'company_types', 'resume_hooks', 'harsh_status', 'answer', 'keywords',
                 'followups', 'trap', 'fs_link', 'code', 'verify', 'notes', 'section', 'section_title',
                 'hot_score', 'score_factors']

# Score = R x E x H x L (see publication.score_rule in data/meta.json).
EVIDENCE_SCORE = {'E3': 4, 'E2': 3, 'E1': 2}
E0_FREQUENCY_SCORE = {'est. very common': 2, 'est. common': 1.5, 'est. occasional': 1}
STATUS_SCORE = {'GAP': 4, 'SHAKY': 3, 'UNTESTED': 2, 'STRONG': 1}
LEVEL_SCORE = {'L1': 1, 'L2': 2, 'L3': 2, 'L4': 1}
EVIDENCE_LEVELS = {'E0', *EVIDENCE_SCORE}
ID_PATTERN = re.compile(r'JH-(S\d\d)-\d{3}')
HOT_LIST_SIZE = 100


class BuildError(Exception):
    pass


def to_cell(column, value):
    """Turn a question field into CSV cell text (inverse of from_cell)."""
    if column in LIST_COLUMNS:
        return LIST_SEPARATOR.join(value)
    if column in JSON_COLUMNS:
        return json.dumps(value, ensure_ascii=False) if value else ''
    return '' if value is None else value


def from_cell(column, text):
    if column in LIST_COLUMNS:
        return [item.strip() for item in text.split('|') if item.strip()]
    if column in JSON_COLUMNS:
        if not text.strip():
            return None if column == 'code' else []
        return json.loads(text)
    if column == 'fs_link':
        return text or None
    return text


def format_factor(value):
    return str(int(value)) if float(value).is_integer() else str(value)


def read_questions(meta):
    section_titles = {section['id']: section['title'] for section in meta['sections']}
    source_ids = {source['id'] for source in meta['sources']}
    errors = []
    questions = []
    seen = {}
    with open(QUESTIONS_CSV, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        missing = [column for column in COLUMNS if column not in header]
        unknown = [column for column in header if column not in COLUMNS]
        if missing or unknown:
            raise BuildError(f'{QUESTIONS_CSV.name} header: missing columns {missing}, unknown columns {unknown}')
        for row_number, row in enumerate(reader, start=2):  # row 1 is the header, as in a spreadsheet
            if not any((value or '').strip() for value in row.values()):
                continue
            where = f'row {row_number} ({row.get("id") or "no id"})'
            question = {}
            for column in COLUMNS:
                text = row.get(column) or ''
                if column not in JSON_COLUMNS and column != 'answer':
                    text = text.strip()
                if column in REQUIRED_COLUMNS and not text.strip():
                    errors.append(f'{where}: "{column}" is empty')
                try:
                    question[column] = from_cell(column, text)
                except json.JSONDecodeError as error:
                    errors.append(f'{where}: "{column}" is not valid JSON ({error})')
                    question[column] = from_cell(column, '')
            errors.extend(f'{where}: {message}' for message in check_question(question, section_titles, source_ids))
            if question['id'] in seen:
                errors.append(f'{where}: duplicate id, already used on row {seen[question["id"]]}')
            seen[question['id']] = row_number
            questions.append(question)
    if errors:
        raise BuildError('\n'.join(errors))
    return questions


def check_question(question, section_titles, source_ids):
    match = ID_PATTERN.fullmatch(question['id'])
    if not match:
        yield f'id must look like JH-S05-017, got "{question["id"]}"'
    elif match.group(1) not in section_titles:
        yield f'section {match.group(1)} from the id is not in data/meta.json "sections"'
    if question['level'] not in LEVEL_SCORE:
        yield f'level must be one of {sorted(LEVEL_SCORE)}, got "{question["level"]}"'
    if question['evidence'] not in EVIDENCE_LEVELS:
        yield f'evidence must be one of {sorted(EVIDENCE_LEVELS)}, got "{question["evidence"]}"'
    elif question['evidence'] == 'E0' and question['frequency'] not in E0_FREQUENCY_SCORE:
        yield f'frequency for E0 must be one of {list(E0_FREQUENCY_SCORE)}, got "{question["frequency"]}"'
    if question['harsh_status'] not in STATUS_SCORE:
        yield f'harsh_status must be one of {list(STATUS_SCORE)}, got "{question["harsh_status"]}"'
    for hook in question['resume_hooks']:
        if not hook.startswith('R:'):
            yield f'resume hook "{hook}" must start with "R:"'
    if not isinstance(question['companies'], list):
        yield 'companies must be a JSON list like [{"name": "Accolite", "sources": ["S010"], "year": null}]'
    else:
        for company in question['companies']:
            if not isinstance(company, dict) or not company.get('name') or not isinstance(company.get('sources'), list):
                yield f'company entry {json.dumps(company)} needs "name" and a "sources" list'
                continue
            company.setdefault('year', None)
            for source in company['sources']:
                if source not in source_ids:
                    yield f'company {company["name"]} cites source "{source}", which is not in data/meta.json "sources"'
    if not isinstance(question['followups'], list) or not all(
            isinstance(item, dict) and set(item) == {'q', 'a'} for item in question['followups']):
        yield 'followups must be a JSON list like [{"q": "...", "a": "..."}]'
    if question['code'] is not None and not isinstance(question['code'], dict):
        yield 'code must be empty or a JSON object'


def score(question):
    factors = [
        2 if question['resume_hooks'] else 1,
        EVIDENCE_SCORE.get(question['evidence']) or E0_FREQUENCY_SCORE[question['frequency']],
        STATUS_SCORE[question['harsh_status']],
        LEVEL_SCORE[question['level']],
    ]
    total = 1
    for factor in factors:
        total *= factor
    return total, ' x '.join(format_factor(factor) for factor in factors)


def build_handbook(meta, rows):
    section_titles = {section['id']: section['title'] for section in meta['sections']}
    questions = []
    for row in rows:
        section = ID_PATTERN.fullmatch(row['id']).group(1)
        hot_score, score_factors = score(row)
        derived = {'section': section, 'section_title': section_titles[section],
                   'hot_score': hot_score, 'score_factors': score_factors}
        questions.append({key: derived[key] if key in derived else row[key] for key in QUESTION_KEYS})
    questions.sort(key=lambda question: question['id'])
    known_ids = {question['id'] for question in questions}

    publication = meta['publication']
    errors = []

    def check_ids(ids, where):
        errors.extend(f'data/meta.json {where} links to {question_id}, which is not in {QUESTIONS_CSV.name}'
                      for question_id in ids if question_id not in known_ids)

    resume_triggers = []
    for trigger in publication['resume_triggers']:
        check_ids(trigger['direct_ids'], f'resume trigger {trigger["id"]} direct_ids')
        hooks = set(trigger['hooks'])
        resume_triggers.append({
            'id': trigger['id'], 'bullet': trigger['bullet'], 'gap': trigger.get('gap'),
            'direct_ids': trigger['direct_ids'],
            'question_ids': [question['id'] for question in questions
                             if hooks & set(question['resume_hooks']) or question['id'] in trigger['direct_ids']],
        })
    for playbook in publication['priority_playbooks']:
        check_ids(playbook['prepare_first'], f'playbook "{playbook["company"]}" prepare_first')
    if errors:
        raise BuildError('\n'.join(errors))

    gap_drills = {}
    for question in questions:
        if question['harsh_status'] in ('GAP', 'SHAKY'):
            gap_drills.setdefault(question['topic'], []).append(question['id'])

    sources = []
    for source in meta['sources']:
        entry = {}
        for key, value in source.items():
            entry[key] = value
            if key == 'independence_group':
                entry['supported_question_ids'] = [
                    question['id'] for question in questions
                    if any(source['id'] in company['sources'] for company in question['companies'])]
        sources.append(entry)

    counts = {}
    for question in questions:
        counts[question['section']] = counts.get(question['section'], 0) + 1
    total = len(questions)
    in_target = publication['target_min'] <= total <= publication['target_max']
    scope_notice = publication['scope_notice_template'].format(
        total=total,
        sections=len(meta['sections']),
        target_status='Count target met' if in_target else 'Count target not met',
        target_min=publication['target_min'],
        target_max=publication['target_max'],
        executed=sum(1 for question in questions if question['code'] and question['code'].get('executed')),
        verify_open=sum(len(question['verify']) for question in questions),
    )

    return {
        'questions': questions,
        'sources': sources,
        'publication': {
            'edition': publication['edition'],
            'target_min': publication['target_min'],
            'target_max': publication['target_max'],
            'scope_notice': scope_notice,
            'score_rule': publication['score_rule'],
            'section_targets': {section['id']: section['target'] for section in meta['sections']},
            'resume_triggers': publication['resume_triggers'],
            'priority_playbooks': publication['priority_playbooks'],
        },
        'indexes': {
            'hot_list': [{key: question[key] for key in
                          ('id', 'question', 'hot_score', 'score_factors', 'section', 'harsh_status')}
                         for question in sorted(questions, key=lambda q: (-q['hot_score'], q['id']))[:HOT_LIST_SIZE]],
            'resume_triggers': resume_triggers,
            'gap_drills': [{'topic': topic, 'question_ids': gap_drills[topic]}
                           for topic in sorted(gap_drills, key=str.casefold)],
            'coverage': [{'id': section['id'], 'title': section['title'],
                          'count': counts.get(section['id'], 0), 'target': section['target']}
                         for section in meta['sections']],
            'company_coverage': [{'company': company['name'], 'question_id': question['id'],
                                  'evidence': question['evidence']}
                                 for question in questions for company in question['companies']],
        },
        'stack': meta['stack'],
    }


def read_text(path):
    with open(path, encoding='utf-8', newline='') as f:  # keep line endings exactly as stored
        return f.read()


def render(handbook, section_count):
    template = read_text(TEMPLATE_HTML)
    for placeholder in (DATA_PLACEHOLDER, SECTIONS_PLACEHOLDER):
        if template.count(placeholder) != 1:
            raise BuildError(f'{TEMPLATE_HTML.name} must contain {placeholder} exactly once')
    # Escape <, > and & so question text can never close the <script> tag early.
    data = (json.dumps(handbook, ensure_ascii=True, separators=(',', ':'))
            .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026'))
    return template.replace(DATA_PLACEHOLDER, data).replace(SECTIONS_PLACEHOLDER, str(section_count))


def main(argv):
    check_only = '--check' in argv
    try:
        meta = json.loads(read_text(META_JSON))
        handbook = build_handbook(meta, read_questions(meta))
        html = render(handbook, len(meta['sections']))
    except BuildError as error:
        print(f'Build failed:\n{error}', file=sys.stderr)
        return 1
    current = read_text(OUTPUT_HTML) if OUTPUT_HTML.exists() else None
    summary = f'{len(handbook["questions"])} questions, {len(meta["sections"])} sections'
    if check_only:
        if html != current:
            print(f'index.html is out of date with data/ ({summary}). Run: python build/build.py', file=sys.stderr)
            return 1
        print(f'index.html is up to date ({summary}).')
        return 0
    if html == current:
        print(f'index.html already up to date ({summary}).')
    else:
        with open(OUTPUT_HTML, 'w', encoding='utf-8', newline='') as f:
            f.write(html)
        print(f'Wrote index.html ({summary}).')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

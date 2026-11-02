"""Actual prompt/glossary identity without importing an SDK into the API."""
import ast
import hashlib
import json
from src.doctor import ROOT,read_config
from src.glossary import Glossary
from src.languages import source_prompt


def prompt(entries, source_language='en'):
    tree=ast.parse((ROOT/'src/translator.py').read_text())
    text=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SYSTEM_TRANSLATE_PROMPT' for t in node.targets))
    text=source_prompt(text,source_language)
    glossary=Glossary();glossary.entries={e['en']:e['vi'] for e in entries}
    instruction=glossary.to_prompt_instruction()
    return text+('\n\n'+instruction if instruction else '')


def identity(values,entries,verification,source_language='en'):
    glossary_hash=hashlib.sha256(json.dumps(entries,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    prompt_hash=hashlib.sha256(prompt(entries,source_language).encode()).hexdigest()
    endpoint=hashlib.sha256((read_config().get('OPENAI_BASE_URL') or 'https://api.openai.com/v1').encode()).hexdigest()
    fingerprint=hashlib.sha256(json.dumps([values['translation_model'],values['chunk_chars'],glossary_hash,prompt_hash,endpoint,verification]).encode()).hexdigest()
    return {'glossary_hash':glossary_hash,'prompt_hash':prompt_hash,'translation_fingerprint':fingerprint}

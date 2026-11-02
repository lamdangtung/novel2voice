"""Source-language catalog shared by API validation, database and translation prompts."""
LANGUAGES = {
    'vi': 'Tiếng Việt', 'en': 'Tiếng Anh', 'zh': 'Tiếng Trung',
    'ja': 'Tiếng Nhật', 'ko': 'Tiếng Hàn', 'fr': 'Tiếng Pháp',
    'de': 'Tiếng Đức', 'es': 'Tiếng Tây Ban Nha', 'pt': 'Tiếng Bồ Đào Nha',
    'it': 'Tiếng Ý', 'ru': 'Tiếng Nga', 'th': 'Tiếng Thái',
    'id': 'Tiếng Indonesia', 'ms': 'Tiếng Malaysia', 'hi': 'Tiếng Hindi',
    'ar': 'Tiếng Ả Rập', 'tr': 'Tiếng Thổ Nhĩ Kỳ', 'uk': 'Tiếng Ukraina',
    'pl': 'Tiếng Ba Lan', 'nl': 'Tiếng Hà Lan', 'sv': 'Tiếng Thụy Điển',
    'fi': 'Tiếng Phần Lan',
}


def validate_language(value):
    if value not in LANGUAGES:
        raise ValueError('Ngôn ngữ chưa có trong danh sách hỗ trợ.')
    return value


def source_prompt(prompt, language='en'):
    validate_language(language)
    return prompt if language == 'en' else prompt.replace('từ tiếng Anh sang tiếng Việt', f'từ {LANGUAGES[language][0].lower() + LANGUAGES[language][1:]} sang tiếng Việt')

from decouple import config

RULES = {
    'food': [
        'hungerstation', 'keeta', 'mcdonald', 'dominos', 'al tazaj', 'kudu',
        'كودو', 'تازج', 'هنقرستيشن', 'جاهز', 'jahez', 'ninja', 'مطعم',
        'برغر', 'شاورما', 'بيتزا', 'starbucks', 'tim hortons', 'coffee',
        'keemart', 'shawerma', 'express food', 'white heart', 'restaurant',
        'cafe', 'كافيه', 'مقهى', 'حلويات', 'sweets', 'bakery', 'مخبز',
    ],
    'fuel': [
        'aldrees', 'الدريس', 'petro', 'fuel', 'وقود', 'بنزين',
        'ساسكو', 'sasco', 'naft services', 'gas station',
    ],
    'pharmacy': [
        'alnahdi', 'النهدي', 'nahdi', 'lemon', 'ليمون', 'niceone',
        'صيدلية', 'pharmacy', 'medical', 'طبي', 'whites', 'dawaa',
        'drug', 'clinic', 'عيادة', 'hospital', 'مستشفى',
    ],
    'shopping': [
        'panda', 'بنده', 'danube', 'الدانوب', 'carrefour', 'zara',
        'h&m', 'centrepoint', 'سنتربوينت', 'namshi', 'noon', 'amazon',
        'shein', 'ikea', 'next', 'jafza', 'extra', 'jarir', 'جرير',
        'hypermarket',
    ],
    'bills': [
        'سداد', 'sadad', 'stc', 'mobily', 'زين', 'zain', 'tiqmo',
        'تيقمو', 'barq', 'برق', 'maharah', 'electricity', 'كهرباء',
        'water', 'ماء', 'internet', 'انترنت', 'bill', 'فاتورة',
    ],
    'family': [
        'تحويل الى الاهل', 'تحويل لأفراد الأسرة',
        'transfer to family', 'الأهل والاصدقاء',
        'تحويل الى الاهل والاصدقاء',
    ],
    'bnpl': [
        'tabby', 'تابي', 'tamara', 'تمارا',
    ],
    'salary': [
        'payroll', 'رواتب', 'إيداع رواتب', 'salary',
        'petro rabigh', 'riblsari', 'راتب',
    ],
    'investment': [
        'malaa', 'ملاء', 'استثمار', 'investment',
        'الأهلي كابيتال', 'capital', 'صندوق', 'fund',
    ],
}


def rule_based_classify(sms_text: str) -> str:
    text_lower = sms_text.lower()
    for category, keywords in RULES.items():
        if any(kw.lower() in text_lower for kw in keywords):
            return category
    return 'other'


def gemini_classify(sms_text: str) -> str:
    try:
        import google.generativeai as genai  # lazy import — only when needed
        api_key = config('GEMINI_API_KEY', default='')
        if not api_key:
            return 'other'
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(
            f"""صنّف هذه العملية البنكية في إحدى هذه الفئات فقط:
food | fuel | pharmacy | shopping | bills | family | bnpl | investment | salary | other

SMS: {sms_text}

أجب بكلمة واحدة فقط من القائمة."""
        )
        result = response.text.strip().lower()
        valid = ['food', 'fuel', 'pharmacy', 'shopping', 'bills',
                 'family', 'bnpl', 'investment', 'salary', 'other']
        return result if result in valid else 'other'
    except BaseException:
        return 'other'


def classify(sms_text: str) -> str:
    result = rule_based_classify(sms_text)
    if result == 'other':
        result = gemini_classify(sms_text)
    return result

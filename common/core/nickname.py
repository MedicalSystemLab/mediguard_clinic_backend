import random

ADJECTIVES = [
    "행복한", "즐거운", "빛나는", "맑은", "푸른", "따뜻한", "부드러운", "강한", "용감한", "지혜로운",
    "신비로운", "아름다운", "친절한", "활기찬", "조용한", "차분한", "열정적인", "우아한", "멋진", "자유로운"
]

NOUNS = [
    "사자", "호랑이", "독수리", "고래", "돌고래", "사슴", "다람쥐", "토끼", "강아지", "고양이",
    "별", "달", "햇살", "구름", "바다", "강", "산", "나무", "꽃", "바람", "하늘", "숲", "이슬", "무지개"
]

def generate_random_nickname() -> str:
    """한국어 형용사와 명사를 조합하고 랜덤 숫자 4자리를 추가하여 임의의 닉네임을 생성합니다."""
    adjective = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    random_number = random.randint(1000, 9999)
    return f"{adjective}{noun}{random_number}"

from backend.audio.text import chunk_text, split_sentences
from backend.validation import normalize_text, safe_filename


def test_paragraphs_are_split_regression():
    """The original prototype's regex had doubled backslashes and never split."""
    text = "First paragraph here.\n\nSecond paragraph here."
    chunks = chunk_text(normalize_text(text), max_chars=500)
    assert [c.text for c in chunks] == ["First paragraph here.", "Second paragraph here."]
    assert all(c.paragraph_end for c in chunks)


def test_sentences_split_and_abbreviations_kept():
    s = split_sentences("Dr. Smith arrived. He said hello! Did you hear? Yes.")
    assert s == ["Dr. Smith arrived.", "He said hello!", "Did you hear?", "Yes."]


def test_chunks_respect_limits_and_order():
    sentence = "This is a reasonably ordinary sentence with some words in it. "
    text = (sentence * 40).strip()
    chunks = chunk_text(text, max_chars=300, first_chars=120)
    assert len(chunks[0].text) <= 120
    assert all(len(c.text) <= 300 for c in chunks)
    assert " ".join(c.text for c in chunks) == text            # nothing lost or reordered
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert sum(c.paragraph_end for c in chunks) == 1


def test_overlong_sentence_is_cut_not_dropped():
    text = "word " * 400
    chunks = chunk_text(text.strip(), max_chars=200)
    assert all(len(c.text) <= 200 for c in chunks)
    assert sum(len(c.text.split()) for c in chunks) == 400


def test_unspaced_cjk_is_chunked():
    text = "你好。" * 200
    chunks = chunk_text(text, max_chars=100)
    assert len(chunks) > 1 and all(len(c.text) <= 100 for c in chunks)


def test_normalize_is_non_semantic():
    assert normalize_text("a \t b\r\nc\x00  \n\n\n\nd") == "a b\nc\n\nd"
    assert normalize_text("Costs $5.00, 3 > 2.") == "Costs $5.00, 3 > 2."


def test_safe_filename():
    assert safe_filename("../../etc/passwd") == "etc-passwd"
    assert safe_filename('a<b>c:"d"|e?*') == "a-b-c-d-e"
    assert safe_filename("CON").upper() != "CON"
    assert safe_filename("   ...   ") == "echolade-voiceover"
    assert len(safe_filename("x" * 500)) <= 80
    assert "/" not in safe_filename("a/b\\c") and "\\" not in safe_filename("a/b\\c")

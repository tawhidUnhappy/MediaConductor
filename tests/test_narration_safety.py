"""Unit tests for narration delivery and fluency lints."""

from mangaeasy.audio.narration_safety import (
    narration_delivery_lint,
    narration_fluency_lint,
)


def test_narration_delivery_lint_flags_spaced_laugh():
    lint = narration_delivery_lint("Ha ha ha, you fool!")
    assert lint is not None


def test_narration_delivery_lint_flags_concatenated_laugh():
    lint = narration_delivery_lint("Hahaha, is that all you got?")
    assert lint is not None
    assert narration_delivery_lint("GHAHA, the phoenix has returned.") is not None


def test_narration_delivery_lint_flags_elongated_scream():
    assert narration_delivery_lint("AAAAAH! Run!") is not None
    assert narration_delivery_lint("aaaargh, my arm!") is not None
    assert narration_delivery_lint("Argh. He falls back.") is not None
    assert narration_delivery_lint("Ugh. He catches his breath.") is not None
    assert narration_delivery_lint("Grr. The beast watches him.") is not None
    assert narration_delivery_lint("Gha ha. The phoenix watches them.") is not None
    assert narration_delivery_lint("Nooooo... he refuses to believe it.") is not None
    assert narration_delivery_lint("Nooo... he refuses to believe it.") is not None
    assert narration_delivery_lint("Pleeease, he asks quietly.") is not None
    assert narration_delivery_lint("Sooo, the meeting continues.") is not None


def test_narration_delivery_lint_flags_loud_typography():
    assert narration_delivery_lint("The battle begins!") is not None
    assert narration_delivery_lint("He orders them to STOP before the gate closes.") is not None
    assert narration_delivery_lint("THE PHOENIX HAS RETURNED.") is not None
    assert narration_delivery_lint("PHOENIX POWER AWAKENS.") is not None
    assert narration_delivery_lint("DRAGON KNIGHT RETURNS.") is not None
    assert narration_delivery_lint("BIG LOUD WORDS.") is not None
    for shout in ("NO.", "GO.", "YES.", "FIRE.", "ENOUGH."):
        assert narration_delivery_lint(shout) is not None
    assert narration_delivery_lint("What?? He cannot understand the result.") is not None


def test_narration_delivery_lint_allows_real_words_and_interjections():
    assert narration_delivery_lint("Hmm, even though he tried, it failed.") is None
    assert narration_delivery_lint("He said hi to his friend.") is None
    assert narration_delivery_lint("She laughed nervously.") is None
    assert narration_delivery_lint("The NPC walks away quietly.") is None
    assert narration_delivery_lint("Aoi enters the room calmly.") is None
    assert narration_delivery_lint("NASA publishes the result in HTML for the MMORPG community.") is None
    assert narration_delivery_lint("US NATO HQ shares a NASA HTML API report.") is None
    assert narration_delivery_lint("") is None


def test_narration_fluency_lint_flags_stammered_prefix():
    assert narration_fluency_lint("Th- This is...?") is not None
    assert narration_fluency_lint("Cy- Cyril-sama...?") is not None


def test_narration_fluency_lint_flags_repeated_word():
    assert narration_fluency_lint("I... I guess...") is not None
    assert narration_fluency_lint("The... the artifact?") is not None
    assert narration_fluency_lint("Of... of course. He agrees.") is not None
    assert narration_fluency_lint("He said that that was wrong.") is not None
    assert narration_fluency_lint("W... w... well... It is...") is not None


def test_narration_fluency_lint_flags_dead_pauses_and_bare_dashes():
    assert narration_fluency_lint("I... ...so that was what happened.") is not None
    assert narration_fluency_lint("Could she be-") is not None
    assert narration_fluency_lint("The droplet pulses with light—") is not None


def test_narration_fluency_lint_flags_contentless_fragments():
    assert narration_fluency_lint("Huh...") is not None
    assert narration_fluency_lint("Um...") is not None
    assert narration_fluency_lint("Is that...") is not None
    assert narration_fluency_lint("The princess...?") is not None


def test_narration_fluency_lint_allows_ordinary_prose():
    assert narration_fluency_lint("He stares, startled by what he is seeing.") is None
    assert narration_fluency_lint("She agrees, though without much confidence.") is None
    # One ellipsis inside a real sentence is a pause, not a stammer.
    assert narration_fluency_lint("He hesitates... then finally answers her.") is None
    # Hyphenated compounds are not stammers.
    assert narration_fluency_lint("He is now a one-star dragon knight.") is None
    assert narration_fluency_lint("Lindworm keeps several B-rank knights.") is None
    assert narration_fluency_lint("The dragon stops mid-sentence, clearly shocked.") is None
    # Legitimate doubled words that are not function-word stammers.
    assert narration_fluency_lint("She waves and says bye bye now.") is None
    assert narration_fluency_lint("") is None

from argparse import Namespace

import pytest

from mediaconductor.video_pipeline import audio_takes, cleanup_audio


def _args(tmp_path, *, yes=False, purge=False):
    project_root = tmp_path / "content"
    project_root.mkdir()
    return Namespace(
        project_root=project_root,
        audio_root=tmp_path / "audio",
        project_name="Story",
        items=["01"],
        item_range=None,
        include_legacy=False,
        purge=purge,
        yes=yes,
    )


def _make_audio(args):
    project_audio = args.audio_root / args.project_name
    chapter_audio = project_audio / "01"
    chapter_audio.mkdir(parents=True)
    (chapter_audio / "panel.wav").write_bytes(b"panel audio")
    other_chapter = project_audio / "02"
    other_chapter.mkdir()
    (other_chapter / "panel.wav").write_bytes(b"other panel")
    combined_root = project_audio / "_items"
    combined_root.mkdir()
    combined = combined_root / "item_01_narration.wav"
    combined.write_bytes(b"combined audio")
    other_combined = combined_root / "item_02_narration.wav"
    other_combined.write_bytes(b"other combined")
    return project_audio, chapter_audio, combined, other_chapter, other_combined


def test_selected_cleanup_dry_run_includes_combined_audio_without_moving_it(tmp_path, monkeypatch, capsys):
    args = _args(tmp_path)
    _, chapter_audio, combined, _, _ = _make_audio(args)
    monkeypatch.setattr(cleanup_audio, "parse_args", lambda: args)

    assert cleanup_audio.main() == 0

    output = capsys.readouterr().out
    assert str(chapter_audio) in output
    assert str(combined) in output
    assert chapter_audio.is_dir()
    assert combined.is_file()
    assert not (args.audio_root / args.project_name / "old").exists()


def test_selected_cleanup_archives_chapter_and_combined_audio_in_restorable_layout(tmp_path, monkeypatch):
    args = _args(tmp_path, yes=True)
    project_audio, chapter_audio, combined, other_chapter, other_combined = _make_audio(args)
    monkeypatch.setattr(cleanup_audio, "parse_args", lambda: args)

    assert cleanup_audio.main() == 0

    run_dir = project_audio / "old" / "run_0001"
    assert not chapter_audio.exists()
    assert not combined.exists()
    assert (run_dir / "01" / "panel.wav").read_bytes() == b"panel audio"
    assert (run_dir / "_items" / "item_01_narration.wav").read_bytes() == b"combined audio"
    assert (other_chapter / "panel.wav").read_bytes() == b"other panel"
    assert other_combined.read_bytes() == b"other combined"


def test_selected_cleanup_purge_deletes_chapter_and_combined_audio_only(tmp_path, monkeypatch):
    args = _args(tmp_path, yes=True, purge=True)
    project_audio, chapter_audio, combined, other_chapter, other_combined = _make_audio(args)
    monkeypatch.setattr(cleanup_audio, "parse_args", lambda: args)

    assert cleanup_audio.main() == 0

    assert not chapter_audio.exists()
    assert not combined.exists()
    assert (other_chapter / "panel.wav").is_file()
    assert other_combined.is_file()
    assert not (project_audio / "old").exists()


def test_selected_cleanup_finds_stale_combined_audio_after_chapter_folder_is_gone(tmp_path, monkeypatch):
    args = _args(tmp_path, yes=True)
    project_audio, chapter_audio, combined, _, _ = _make_audio(args)
    for panel_audio in chapter_audio.iterdir():
        panel_audio.unlink()
    chapter_audio.rmdir()
    monkeypatch.setattr(cleanup_audio, "parse_args", lambda: args)

    assert cleanup_audio.main() == 0

    assert not combined.exists()
    assert (project_audio / "old" / "run_0001" / "_items" / combined.name).read_bytes() == b"combined audio"


def test_cleanup_resolves_numeric_selection_to_actual_item_folder_name(tmp_path):
    args = _args(tmp_path)
    args.items = ["1"]
    (args.project_root / "1").mkdir()
    project_audio = args.audio_root / args.project_name
    chapter_audio = project_audio / "1"
    chapter_audio.mkdir(parents=True)
    combined = project_audio / "_items" / "item_1_narration.wav"
    combined.parent.mkdir()
    combined.write_bytes(b"combined")

    targets = cleanup_audio.safe_generated_audio_targets(args)

    assert targets == [chapter_audio.resolve(), combined.resolve()]


def test_cleanup_keeps_explicit_stale_target_when_another_source_item_resolves(tmp_path):
    args = _args(tmp_path)
    args.items = ["01", "99"]
    (args.project_root / "01").mkdir()
    project_audio = args.audio_root / args.project_name
    live_audio = project_audio / "01"
    stale_audio = project_audio / "99"
    live_audio.mkdir(parents=True)
    stale_audio.mkdir()
    stale_combined = project_audio / "_items" / "item_99_narration.wav"
    stale_combined.parent.mkdir()
    stale_combined.write_bytes(b"stale")

    targets = cleanup_audio.safe_generated_audio_targets(args)

    assert targets == [live_audio.resolve(), stale_audio.resolve(), stale_combined.resolve()]


def test_cleanup_rejects_selected_item_linked_into_sibling_project(tmp_path):
    args = _args(tmp_path)
    sibling = args.audio_root / "OtherStory" / "01"
    sibling.mkdir(parents=True)
    project_audio = args.audio_root / args.project_name
    project_audio.mkdir(parents=True)
    try:
        (project_audio / "01").symlink_to(sibling, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")

    with pytest.raises(ValueError, match="unsafe path"):
        cleanup_audio.safe_generated_audio_targets(args)


def test_targeted_cleanup_and_restore_round_trip_combined_audio(tmp_path, monkeypatch):
    cleanup_args = _args(tmp_path, yes=True)
    project_audio, chapter_audio, combined, _, _ = _make_audio(cleanup_args)
    monkeypatch.setattr(cleanup_audio, "parse_args", lambda: cleanup_args)
    assert cleanup_audio.main() == 0

    chapter_audio.mkdir()
    (chapter_audio / "panel.wav").write_bytes(b"new active panel")
    combined.parent.mkdir(exist_ok=True)
    combined.write_bytes(b"new active combined")
    restore_args = Namespace(
        project_root=cleanup_args.project_root,
        audio_root=cleanup_args.audio_root,
        project_name=cleanup_args.project_name,
        run="run_0001",
        items=["01"],
    )
    monkeypatch.setattr(audio_takes, "restore_main_args", lambda: restore_args)

    assert audio_takes.restore_main() == 0

    assert (chapter_audio / "panel.wav").read_bytes() == b"panel audio"
    assert combined.read_bytes() == b"combined audio"
    assert (project_audio / "old" / "run_0002" / "01" / "panel.wav").read_bytes() == b"new active panel"
    assert (
        project_audio / "old" / "run_0002" / "_items" / "item_01_narration.wav"
    ).read_bytes() == b"new active combined"

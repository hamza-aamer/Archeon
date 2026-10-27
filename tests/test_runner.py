import sys
import threading
import time

import pytest

from archeon.pipeline.base import Cancelled, SceneLayout, StageContext, StageError, fraction_parser
from archeon.presets import PRESETS


@pytest.fixture
def ctx(settings, tmp_path):
    layout = SceneLayout(tmp_path / "scene")
    layout.root.mkdir(parents=True)
    seen = []
    context = StageContext(settings, layout, PRESETS["preview"], on_progress=seen.append)
    context.seen = seen
    return context


def python(code):
    return [sys.executable, "-c", code]


def output_lines(ctx):
    """Log lines produced by the command itself (the `$ cmd` echo is excluded)."""
    return [line for line in ctx.layout.log.read_text().splitlines() if not line.startswith("[archeon] $")]


def test_fraction_parser_variants():
    sugar = fraction_parser(r"\[\s*(\d+)/\s*(\d+)\]")
    assert sugar("loss: 0.0123  [ 1200/15000]") == pytest.approx(0.08)
    assert sugar("nothing here") is None
    tqdm = fraction_parser(r"Training progress:\s*(\d+)%", total=100)
    assert tqdm("Training progress:  45%|####      | 3150/7000") == pytest.approx(0.45)
    resumed = fraction_parser(r"\[\s*(\d+)/\s*(\d+)\]", relative=True)
    assert resumed("loss: 0.03  [ 7000/15000]") == pytest.approx(0.0)
    assert resumed("loss: 0.02  [11000/15000]") == pytest.approx(0.5)


def test_run_streams_log_and_progress(ctx):
    code = (
        "import sys\n"
        "for i in range(1, 5):\n"
        "    sys.stdout.write(f'step [{i}/4]\\r'); sys.stdout.flush()\n"
        "print('\\x1b[32mfinished\\x1b[0m')\n"
    )
    ctx.run(python(code), parser=fraction_parser(r"\[(\d+)/(\d+)\]"), segment=(0.5, 1.0))
    assert ctx.seen[-1] == pytest.approx(1.0)
    assert ctx.seen[0] == pytest.approx(0.625)
    lines = output_lines(ctx)
    assert lines[-1] == "finished" and not any("\x1b" in line for line in lines)
    assert sum(line.startswith("step [") for line in lines) == 1  # carriage-return redraws are throttled


def test_hidden_lines_feed_parser_but_not_log(ctx):
    ctx.run(python("print('progress=50'); print('kept')"),
            parser=lambda line: 0.5 if line == "progress=50" else None, hide=r"^progress=")
    assert output_lines(ctx) == ["kept"]
    assert ctx.seen == [0.5]


def test_failure_raises_stage_error_with_last_line(ctx):
    with pytest.raises(StageError, match="something broke"):
        ctx.run(python("import sys; print('something broke'); sys.exit(3)"))


def test_out_of_memory_gets_friendly_message(ctx):
    with pytest.raises(StageError, match="ran out of memory"):
        ctx.run(python("import sys; print('RuntimeError: CUDA out of memory. Tried to allocate'); sys.exit(1)"))


def test_cancel_kills_process(ctx):
    timer = threading.Timer(0.5, ctx.cancel_event.set)
    timer.start()
    started = time.monotonic()
    with pytest.raises(Cancelled):
        ctx.run(python("import time; time.sleep(30)"))
    assert time.monotonic() - started < 10

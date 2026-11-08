from backend.main import FRONTEND_DIR


def test_unsolved_models_receive_no_winner_medal():
    js = (FRONTEND_DIR / 'app.js').read_text(encoding='utf-8')
    assert "if (!solved) {" in js
    assert "this.q.medal.textContent = '';" in js
    assert "else cards[k]?.setRank(0, false);" in js
    assert "if (r?.solved) cards[k]?.setRank(++solvedRank, true);" in js

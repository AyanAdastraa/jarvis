import pytest
from unittest.mock import patch, MagicMock

@patch("builtins.input", return_value="exit")
@patch("app.main.NemotronProvider")
def test_startup_mocked(mock_provider, mock_input, capsys):
    from app.main import main
    mock_instance = mock_provider.return_value
    mock_instance.health_check.return_value = True
    
    main()
    
    captured = capsys.readouterr()
    assert "JARVIS Phase 3 CLI Initialized" in captured.out
    assert "shutting down" in captured.out

@patch("app.main.NemotronProvider")
def test_startup_failure(mock_provider, capsys):
    from app.main import main
    mock_instance = mock_provider.return_value
    mock_instance.health_check.return_value = False
    
    main()
    
    captured = capsys.readouterr()
    assert "Failed to connect to the model provider" in captured.out


from kokki.tools import system_control, get_system_info


def test_blocks_rm_rf_root():
    result = system_control.invoke({"command": "rm -rf /"})
    assert "BLOCKED" in result


def test_blocks_mkfs():
    result = system_control.invoke({"command": "mkfs.ext4 /dev/sda1"})
    assert "BLOCKED" in result


def test_normal_command_runs():
    result = system_control.invoke({"command": "echo hello"})
    assert "hello" in result


def test_invalid_command_returns_error_not_crash():
    result = system_control.invoke({"command": "this_command_does_not_exist_xyz"})
    assert isinstance(result, str)
    assert "Error" in result


def test_large_output_gets_truncated():
    # yes prints a huge amount of output fast; head -c caps how much we read
    result = system_control.invoke({"command": "yes | head -c 50000"})
    assert len(result) < 2200
    assert "truncated" in result


def test_get_system_info_returns_clean_stats():
    result = get_system_info.invoke({})
    assert "CPU:" in result
    assert "RAM:" in result
    assert "Disk:" in result

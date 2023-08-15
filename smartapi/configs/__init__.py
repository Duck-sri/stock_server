from pathlib import Path

from smartapi.utils import read_toml

config_dir = Path(__file__).parent

angle_config = read_toml(config_dir / 'angle_one_config.toml')
app_config = read_toml(config_dir / 'app.toml')
user_config = read_toml(config_dir / 'user.toml')
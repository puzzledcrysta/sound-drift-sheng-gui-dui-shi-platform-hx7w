from app.settings import KEY, FIELDS, TRACK_FIELD, TRACK_MAIN, TRACK_BACKUP
from app.errors import DataError

# 交接来源在通用声轨字段之外增加轨道角色，其余字段沿用双锚校时契约。
REQUIRED = (KEY, '修订号', '提交时间', TRACK_FIELD, *FIELDS)
TRACKS = (TRACK_MAIN, TRACK_BACKUP)
ALIASES = {'业务编号': KEY, '版本': '修订号', '更新时刻': '提交时间', '备注': '原始备注'}
MISSING = {'', '-', 'n/a', 'null', '未知'}


def mapping(header):
    names = [ALIASES.get(name, name) for name in header]
    if len(set(names)) != len(names) or set(REQUIRED) - set(names):
        raise DataError('CONTRACT', '交接来源缺少必需字段或新旧字段重复')
    return names


def track(value):
    role = value.strip()
    if role not in TRACKS:
        raise DataError('TRACK_ROLE', f'轨道角色须为 {TRACK_MAIN} 或 {TRACK_BACKUP}')
    return role

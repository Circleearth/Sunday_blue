"""Built-in time-context plugin v1: pure, offline, request-scoped system metadata."""
from datetime import datetime

PLUGIN_ID = 'time-context'
VERSION = '1.1.0'

def time_context(moment=None):
    # OS local timezone is authoritative; never label UTC as user local time.
    current = moment if moment is not None else datetime.now().astimezone()
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError('Time context requires a timezone-aware datetime')
    weekdays = ('星期一','星期二','星期三','星期四','星期五','星期六','星期日')
    offset = current.strftime('%z')
    offset = offset[:3] + ':' + offset[3:]
    return (
        '<time_context source="host_clock">\n'
        f'本轮本地日期：{current:%Y-%m-%d}，{weekdays[current.weekday()]}。'
        f'本轮本地时间：{current:%H:%M}，UTC{offset}。\n'
        '这是本轮发送时的系统时间，仅供判断今天、明天、期限和作息；不是用户消息。'
        '不要例行报时、重复日期、每轮问早晚好，也不要无关地劝睡、提醒吃饭。'
        '只有用户询问时间或任务确实需要时才自然提及；不能据此虚构用户活动、离线经历或已设提醒。'
        '旧消息中的今天以当时语境为准，不要把历史相对日期自动改成今天；时区不明的约定先确认。\n'
        '</time_context>'
    )

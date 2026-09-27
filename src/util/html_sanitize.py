from __future__ import annotations

from typing import Final

import nh3

# Разрешённые теги — ровно те, что эмитит TipTap (StarterKit + Underline,
# TaskList/TaskItem, Image, Table, TextStyle/FontSize, Link, CodeBlock).
ALLOWED_TAGS: Final = {
    "a",
    "blockquote",
    "br",
    "code",
    "del",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "img",
    "input",
    "label",
    "li",
    "mark",
    "ol",
    "p",
    "pre",
    "s",
    "span",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}

ALLOWED_ATTRIBUTES: Final = {
    "*": {"class", "style"},
    "a": {"href", "target", "title"},
    "code": {"class"},
    "div": {"style"},
    "h1": {"style"},
    "h2": {"style"},
    "h3": {"style"},
    "h4": {"style"},
    "h5": {"style"},
    "h6": {"style"},
    "img": {"alt", "height", "src", "title", "width"},
    "input": {"checked", "disabled", "type"},
    "li": {"data-checked", "data-type"},
    "ol": {"start"},
    "p": {"style"},
    "pre": {"class"},
    "span": {"style"},
    "table": {"style"},
    "td": {"colspan", "rowspan", "style"},
    "th": {"colspan", "rowspan", "style"},
    "ul": {"data-type"},
}

# Свойства inline-стилей, которые может проставить редактор (FontSize,
# выравнивание). Остальное отбрасывается, чтобы не пропустить url() и
# выражения, которые оживляют старые браузеры.
ALLOWED_STYLE_PROPERTIES: Final = {"font-size", "text-align", "vertical-align"}

# javascript:/data: в ссылках и картинках отсекает url_schemes.
ALLOWED_URL_SCHEMES: Final = {"http", "https", "mailto"}


def sanitize_html(value: str | None) -> str:
    """Очистить HTML перед сохранением.

    Публичные страницы вики читает анонимный посетитель, а фронт рендерит их
    через dangerouslySetInnerHTML, поэтому в базе не должно лежать ничего,
    кроме подмножества вывода редактора.

    Args:
        value: исходный HTML (может быть None)

    Returns:
        Очищенный HTML; пустая строка, если на входе не было содержимого
    """
    if not value:
        return ""

    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        filter_style_properties=ALLOWED_STYLE_PROPERTIES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
        strip_comments=True,
    )

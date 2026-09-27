from __future__ import annotations

from src.util.html_sanitize import sanitize_html


class TestSanitizeHtml:
    def test_should_keep_editor_output(self):
        # given
        value = "<p>Hello <strong>world</strong> <em>и</em> <s>зачёркнуто</s></p>"

        # when
        result = sanitize_html(value)

        # then
        assert result == value

    def test_should_keep_headings_lists_and_quotes(self):
        # given
        value = "<h2>Заголовок</h2><ul><li>раз</li><li>два</li></ul><blockquote>цитата</blockquote>"

        # when
        result = sanitize_html(value)

        # then
        assert result == value

    def test_should_keep_task_list_markup(self):
        # given
        value = (
            '<ul data-type="taskList"><li data-type="taskItem" data-checked="true">'
            '<label><input type="checkbox" checked><span></span></label>'
            "<div><p>сделано</p></div></li></ul>"
        )

        # when
        result = sanitize_html(value)

        # then
        assert 'data-type="taskList"' in result
        assert 'data-checked="true"' in result
        assert "сделано" in result

    def test_should_keep_table_with_span_attributes(self):
        # given
        value = (
            '<table><thead><tr><th colspan="2">h</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>'
        )

        # when
        result = sanitize_html(value)

        # then
        assert result == value

    def test_should_keep_code_block_language_class(self):
        # given
        value = '<pre><code class="language-python">print(1)</code></pre>'

        # when
        result = sanitize_html(value)

        # then
        assert result == value

    def test_should_strip_script(self):
        # given
        value = "<p>ok</p><script>alert(1)</script>"

        # when
        result = sanitize_html(value)

        # then
        assert result == "<p>ok</p>"
        assert "alert" not in result

    def test_should_strip_event_handlers(self):
        # given
        value = '<img src="https://ex.com/a.png" onerror="alert(1)">'

        # when
        result = sanitize_html(value)

        # then
        assert "onerror" not in result
        assert 'src="https://ex.com/a.png"' in result

    def test_should_strip_javascript_url(self):
        # given
        value = '<a href="javascript:alert(1)">click</a>'

        # when
        result = sanitize_html(value)

        # then
        assert "javascript:" not in result
        assert "click" in result

    def test_should_strip_iframe_and_svg(self):
        # given / when
        iframe = sanitize_html('<iframe src="https://evil.com"></iframe>')
        svg = sanitize_html("<svg/onload=alert(1)>")

        # then
        assert iframe == ""
        assert svg == ""

    def test_should_strip_comments(self):
        # given
        value = "<p>ok</p><!-- internal note -->"

        # when
        result = sanitize_html(value)

        # then
        assert result == "<p>ok</p>"

    def test_should_filter_inline_styles(self):
        # given
        value = '<span style="font-size: 14px; background: url(https://evil.com/x)">t</span>'

        # when
        result = sanitize_html(value)

        # then
        assert "font-size:14px" in result
        assert "background" not in result
        assert "evil.com" not in result

    def test_should_add_noopener_to_links_opening_new_tab(self):
        # given
        value = '<a href="https://ex.com" target="_blank">link</a>'

        # when
        result = sanitize_html(value)

        # then
        assert 'rel="noopener noreferrer"' in result

    def test_should_return_empty_string_for_empty_input(self):
        # given / when / then
        assert sanitize_html("") == ""
        assert sanitize_html(None) == ""

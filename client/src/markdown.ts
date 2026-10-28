// Lesson text is written by the agent, so it's rendered with raw HTML off: any HTML in it is
// shown as text, and markdown-it refuses unsafe link targets such as javascript:. Images are
// off too, so a lesson can't load anything from elsewhere.

import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: false, breaks: true }).disable('image')

// Links open in a new tab, so following a source doesn't leave the lesson.
md.renderer.rules.link_open = (tokens, idx, options, _env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return self.renderToken(tokens, idx, options)
}

/** Lesson text as HTML, in paragraphs. */
export function renderMarkdown(text: string): string {
  return md.render(text)
}

/** Lesson text as HTML for a single line, without a paragraph around it. */
export function renderInline(text: string): string {
  return md.renderInline(text)
}

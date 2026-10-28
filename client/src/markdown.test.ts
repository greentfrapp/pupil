import { describe, expect, it } from 'vitest'
import { renderInline, renderMarkdown } from './markdown'

describe('renderMarkdown', () => {
  it('renders emphasis, code and line breaks', () => {
    expect(renderMarkdown('**Vimes** runs `the Watch`\nnow')).toBe(
      '<p><strong>Vimes</strong> runs <code>the Watch</code><br>\nnow</p>\n',
    )
  })

  it('opens links in a new tab', () => {
    expect(renderMarkdown('[Book](https://example.com/b)')).toBe(
      '<p><a href="https://example.com/b" target="_blank" rel="noopener noreferrer">Book</a></p>\n',
    )
  })

  it('shows HTML as text, and refuses unsafe links and images', () => {
    expect(renderMarkdown('<script>x()</script>')).toBe(
      '<p>&lt;script&gt;x()&lt;/script&gt;</p>\n',
    )
    expect(renderMarkdown('[click](javascript:alert(1))')).not.toContain('<a')
    expect(renderMarkdown('![pic](https://example.com/p.png)')).not.toContain('<img')
  })
})

describe('renderInline', () => {
  it('leaves out the paragraph', () => {
    expect(renderInline('Who is *Angua*?')).toBe('Who is <em>Angua</em>?')
  })
})

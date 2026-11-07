import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Research } from '../types'

interface SourceRef {
  title: string
  url: string
}

export function sourceIndex(research: Research | null): Record<string, SourceRef> {
  const out: Record<string, SourceRef> = {}
  if (!research) return out
  for (const s of [...research.web, ...research.books, ...research.videos]) out[s.id] = { title: s.title, url: s.url }
  return out
}

/** Header lines like "**Time:** …" directly under each other belong on separate lines. */
function separateHeaderLines(md: string): string {
  const firstH2 = md.indexOf('\n## ')
  if (firstH2 < 0) return md
  return md.slice(0, firstH2).replace(/\n(?=\*\*)/g, '\n\n') + md.slice(firstH2)
}

/** Turn [S1] into a link the renderer can recognise, but never inside code. */
function linkCitations(md: string): string {
  return separateHeaderLines(md)
    .split(/(```[\s\S]*?```|`[^`\n]*`)/g)
    .map((part, i) => (i % 2 === 1 ? part : part.replace(/\[([SBV]\d+)\](?!\()/g, '[$1](#cite-$1)')))
    .join('')
}

export function Markdown({ text, sources }: { text: string; sources: Record<string, SourceRef> }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a({ href, children }) {
          if (href?.startsWith('#cite-')) {
            const id = href.slice(6)
            const src = sources[id]
            return (
              <sup className={`cite${src ? '' : ' missing'}`}>
                <a
                  href={src?.url ?? '#'}
                  target="_blank"
                  rel="noreferrer"
                  title={src ? src.title : `${id} is not one of the collected sources`}
                >
                  {id}
                </a>
              </sup>
            )
          }
          return (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          )
        },
      }}
    >
      {linkCitations(text)}
    </ReactMarkdown>
  )
}

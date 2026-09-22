import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";

import { preprocessWikilinks, WIKILINK_SCHEME, wikilinkTarget } from "./wikilinkPreprocess";

// react-markdown's default URL sanitizer strips unrecognized schemes (like
// our `wikilink:` one) down to an empty href before any custom renderer
// sees it — let ours through unchanged, defer everything else to the
// default sanitizer so real links stay safe.
function urlTransform(url: string): string {
  return url.startsWith(WIKILINK_SCHEME) ? url : defaultUrlTransform(url);
}

interface MarkdownBodyProps {
  body: string;
  onNavigate: (slug: string) => void;
}

/** Renders a concept's body as Markdown, with `[[wikilink]]`s rendered as
 * in-app navigation instead of dead/external links. */
export function MarkdownBody({ body, onNavigate }: MarkdownBodyProps) {
  const components: Components = {
    a: ({ href, children }) => {
      const target = wikilinkTarget(href);
      if (target) {
        return (
          <button
            onClick={() => onNavigate(target)}
            className="text-spark-dim underline decoration-spark-dim/40 underline-offset-2 hover:text-paper-ink"
          >
            {children}
          </button>
        );
      }
      return (
        <a href={href} target="_blank" rel="noreferrer" className="text-spark-dim underline">
          {children}
        </a>
      );
    },
  };

  return (
    <div className="prose-paper prose prose-base max-w-none font-serif">
      <ReactMarkdown components={components} urlTransform={urlTransform}>
        {preprocessWikilinks(body)}
      </ReactMarkdown>
    </div>
  );
}

import type { ReactNode } from "react";
import { parseMarkdown, type Block, type Inline } from "@/lib/markdown";

/**
 * Renders an assistant reply as formatted text.
 *
 * Builds React elements from `parseMarkdown`'s tree; nothing is ever set as
 * raw HTML. `[UNVERIFIED: …]` flags from `ai.numeric_guard` are highlighted
 * wherever they appear.
 */
export function Markdown({ text }: { text: string }) {
  return <div className="md">{parseMarkdown(text).map(renderBlock)}</div>;
}

function renderBlock(block: Block, key: number): ReactNode {
  switch (block.type) {
    case "heading": {
      // The dialog title is an h2, so reply headings start at h3.
      const level = Math.min(block.level + 2, 6);
      const Tag = `h${level}` as "h3" | "h4" | "h5" | "h6";
      return (
        <Tag key={key} className={`md-h md-h${Math.min(block.level, 3)}`}>
          {renderInlines(block.children)}
        </Tag>
      );
    }
    case "paragraph":
      return <p key={key}>{renderInlines(block.children)}</p>;
    case "code":
      return (
        <pre key={key}>
          <code>{block.text}</code>
        </pre>
      );
    case "hr":
      return <hr key={key} />;
    case "quote":
      return <blockquote key={key}>{block.children.map(renderBlock)}</blockquote>;
    case "list": {
      const items = block.items.map((item, index) => {
        // A tight item (one paragraph, maybe a nested list) needs no <p> wrapper.
        const tight = item.children.filter((child) => child.type === "paragraph").length <= 1;
        return (
          // `value` keeps the number the model wrote instead of renumbering.
          <li key={index} value={item.number}>
            {item.children.map((child, childIndex) =>
              tight && child.type === "paragraph"
                ? renderInlines(child.children)
                : renderBlock(child, childIndex),
            )}
          </li>
        );
      });
      return block.ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>;
    }
    case "table": {
      const cellProps = (column: number) => {
        const align = block.align[column] ?? (block.numeric[column] ? "right" : null);
        return {
          className: block.numeric[column] ? "num" : undefined,
          style: align ? { textAlign: align } : undefined,
        };
      };
      return (
        <div key={key} className="md-table" tabIndex={0} role="region" aria-label="Table">
          <table>
            <thead>
              <tr>
                {block.header.map((cell, column) => (
                  <th key={column} scope="col" {...cellProps(column)}>
                    {renderInlines(cell)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, column) => (
                    <td key={column} {...cellProps(column)}>
                      {renderInlines(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
  }
}

function renderInlines(nodes: Inline[]): ReactNode[] {
  return nodes.map(renderInline);
}

function renderInline(node: Inline, key: number): ReactNode {
  switch (node.type) {
    case "text":
      return node.text;
    case "flag":
      return (
        <span key={key} className="flag" title="This number could not be traced to engine output">
          {node.text}
        </span>
      );
    case "code":
      return <code key={key}>{node.text}</code>;
    case "strong":
      return <strong key={key}>{renderInlines(node.children)}</strong>;
    case "em":
      return <em key={key}>{renderInlines(node.children)}</em>;
    case "del":
      return <del key={key}>{renderInlines(node.children)}</del>;
    case "link":
      return (
        <a key={key} href={node.href} target="_blank" rel="noopener noreferrer">
          {renderInlines(node.children)}
        </a>
      );
    case "br":
      return <br key={key} />;
  }
}

import { Fragment } from "react";

import { splitWords } from "./words";

interface SplitWordsProps {
  text: string;
}

/**
 * Renders each word in a masked span (`.gs-word > span`) so a timeline can slide words up from behind a clip.
 * Words are rendered by React, never split in the DOM afterwards, so re-renders stay safe.
 */
export function SplitWords({ text }: SplitWordsProps) {
  const words = splitWords(text);
  return (
    <>
      {words.map((word, i) => (
        <Fragment key={`${word}-${i}`}>
          <span className="gs-word">
            <span>{word}</span>
          </span>
          {i < words.length - 1 && " "}
        </Fragment>
      ))}
    </>
  );
}

"use client";

import React, { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Thinking from "./Thinking";

export type StreamingMessageHandle = {
  append: (chunk: string) => void;
  reset: () => void;
};

type StreamingMessageProps = {
  onFrame?: () => void;
};

const StreamingMessage = forwardRef<StreamingMessageHandle, StreamingMessageProps>(
  ({ onFrame }, ref) => {
    const bufferRef = useRef("");
    const rafRef = useRef<number | null>(null);
    const [text, setText] = useState("");

    const flush = useCallback(() => {
      rafRef.current = null;
      setText(bufferRef.current);
      onFrame?.();
    }, [onFrame]);

    const scheduleFlush = useCallback(() => {
      if (rafRef.current != null) return;
      rafRef.current = window.requestAnimationFrame(flush);
    }, [flush]);

    const append = useCallback(
      (chunk: string) => {
        if (!chunk) return;
        bufferRef.current = `${bufferRef.current}${chunk}`;
        scheduleFlush();
      },
      [scheduleFlush],
    );

    const reset = useCallback(() => {
      bufferRef.current = "";
      if (rafRef.current != null) {
        window.cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      setText("");
    }, []);

    useImperativeHandle(ref, () => ({ append, reset }), [append, reset]);

    useEffect(() => {
      return () => {
        if (rafRef.current != null) {
          window.cancelAnimationFrame(rafRef.current);
        }
      };
    }, []);

    const hasText = text.trim().length > 0;

    return (
      <div className="inline-flex items-start gap-2">
        {!hasText ? <Thinking /> : null}
        <div className="max-w-[680px] chat-markdown cm-assistant">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {text || " "}
          </ReactMarkdown>
        </div>
      </div>
    );
  },
);

export default memo(StreamingMessage);

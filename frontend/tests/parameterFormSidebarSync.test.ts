import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { act, create } from "react-test-renderer";

import ParameterFormSidebar from "../src/app/dashboard/components/Chat/ParameterFormSidebar";
import type { SealParameters } from "../src/lib/types/sealParameters";

const renderSidebar = (parameters: SealParameters, currentState?: { parameters: SealParameters }) =>
  renderToStaticMarkup(
    React.createElement(ParameterFormSidebar, {
      show: true,
      parameters,
      currentState,
      onFieldChange: () => undefined,
      onSubmit: () => undefined,
      onClose: () => undefined,
    }),
  );

describe("ParameterFormSidebar server-driven updates", () => {
  it("reflects updated pressure_bar values in the rendered input", () => {
    const htmlInitial = renderSidebar({}, { parameters: { pressure_bar: 10 } as SealParameters });
    expect(htmlInitial).toContain('id="param-pressure_bar"');
    expect(htmlInitial).toContain('value="10"');

    const htmlUpdated = renderSidebar({}, { parameters: { pressure_bar: 7 } as SealParameters });
    expect(htmlUpdated).toContain('value="7"');
  });

  it("keeps hook order stable when toggling visibility", () => {
    const baseProps = {
      parameters: {} as SealParameters,
      currentState: { parameters: {} as SealParameters },
      onFieldChange: () => undefined,
      onSubmit: () => undefined,
      onClose: () => undefined,
    };

    const renderer = create(
      React.createElement(ParameterFormSidebar, {
        ...baseProps,
        show: false,
      }),
    );
    expect(renderer.toJSON()).toBeNull();

    act(() => {
      renderer.update(
        React.createElement(ParameterFormSidebar, {
          ...baseProps,
          show: true,
          currentState: { parameters: { pressure_bar: 10 } as SealParameters },
        }),
      );
    });

    const pressureInput = renderer.root.findByProps({ id: "param-pressure_bar" });
    expect(pressureInput.props.value).toBe("10");

    act(() => {
      renderer.update(
        React.createElement(ParameterFormSidebar, {
          ...baseProps,
          show: false,
        }),
      );
    });
    expect(renderer.toJSON()).toBeNull();
  });
});

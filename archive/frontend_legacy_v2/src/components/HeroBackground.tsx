"use client";
import * as React from "react";
import { Canvas, useFrame } from "@react-three/fiber";

const vertexShader = `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
  }
`;

const fragmentShader = `
  varying vec2 vUv;
  uniform float uTime;
  float rand(vec2 co){
      return fract(sin(dot(co.xy,vec2(12.9898,78.233)))*43758.5453);
  }
  float noise(vec2 p){
      vec2 i = floor(p);
      vec2 f = fract(p);
      float a = rand(i);
      float b = rand(i + vec2(1.0, 0.0));
      float c = rand(i + vec2(0.0, 1.0));
      float d = rand(i + vec2(1.0, 1.0));
      vec2 u = f * f * (3.0 - 2.0 * f);
      return mix(a, b, u.x) +
              (c - a)* u.y * (1.0 - u.x) +
              (d - b) * u.x * u.y;
  }
  float fbm(vec2 p) {
      float value = 0.0;
      float amplitude = 0.5;
      for (int i = 0; i < 6; i++) {
          value += amplitude * noise(p);
          p *= 2.0;
          amplitude *= 0.5;
      }
      return value;
  }

  void main() {
    vec2 uv = vUv * 2.0 - 1.0;
    float t = uTime * 0.06;
    float q = fbm(uv * 1.4 + t * 0.6);
    float r = fbm(uv * 2.3 - t * 0.3 + q);
    float mask = smoothstep(0.25, 0.7, r);
    float beam = smoothstep(0.3, 1.0, uv.x + uv.y + 0.5) * 0.6;
    float intensity = (r * 0.7 + q * 0.3) * (1.2 + beam);
    vec3 color = mix(vec3(0.13,0.17,0.26), vec3(0.60,0.75,1.0), intensity);
    color += beam * vec3(1.2,1.2,2.5);
    float alpha = mask * 0.84;
    gl_FragColor = vec4(color, alpha);
  }
`;

export default function HeroBackground() {
  const materialRef = React.useRef<any>(null);
  useFrame(({ clock }) => {
    if (materialRef.current) {
      materialRef.current.uniforms.uTime.value = clock.getElapsedTime();
    }
  });

  return (
    <div className="absolute inset-0 w-full h-full z-0 pointer-events-none">
      <Canvas
        camera={{ position: [0, 0, 1], fov: 40 }}
        style={{ width: "100%", height: "100%" }}
        gl={{ alpha: true, antialias: true }}
      >
        <mesh scale={[3.6, 2.2, 1]}>
          <planeGeometry args={[1, 1, 128, 128]} />
          <shaderMaterial
            ref={materialRef}
            uniforms={{ uTime: { value: 0 } }}
            vertexShader={vertexShader}
            fragmentShader={fragmentShader}
            transparent
            depthWrite={false}
          />
        </mesh>
      </Canvas>
    </div>
  );
}

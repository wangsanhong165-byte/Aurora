// Cubism Core 5.0 → CubismWebFramework-5-r.5 compatibility shim.
//
// The r.5 framework expects a Cubism Core 5.2+ interface, which adds the
// ColorBlendType_* constants (and offscreens / drawable blend modes, handled
// separately in core.ts). Our bundled core is 5.0 (wasm2js) and does not
// expose them. Provide the constants with the standard Live2D values so the
// framework's enums (CubismColorBlend in cubismmodel.ts) resolve at module
// load. Our models use only Normal blend mode, so the values only need to be
// self-consistent (Normal = 0).
(function (C) {
  'use strict';
  if (!C || C.ColorBlendType_Normal !== undefined) {
    return; // real 5.2+ core already provides these
  }
  var v = 0;
  C.ColorBlendType_Normal = v++;             // 0
  C.ColorBlendType_AddCompatible = v++;      // 1
  C.ColorBlendType_MultiplyCompatible = v++; // 2
  C.ColorBlendType_AddGlow = v++;            // 3
  C.ColorBlendType_Add = v++;                // 4
  C.ColorBlendType_Darken = v++;             // 5
  C.ColorBlendType_Multiply = v++;           // 6
  C.ColorBlendType_ColorBurn = v++;          // 7
  C.ColorBlendType_LinearBurn = v++;         // 8
  C.ColorBlendType_Lighten = v++;            // 9
  C.ColorBlendType_Screen = v++;             // 10
  C.ColorBlendType_ColorDodge = v++;         // 11
  C.ColorBlendType_Overlay = v++;            // 12
  C.ColorBlendType_SoftLight = v++;          // 13
  C.ColorBlendType_HardLight = v++;          // 14
  C.ColorBlendType_LinearLight = v++;        // 15
  C.ColorBlendType_Hue = v++;                // 16
  C.ColorBlendType_Color = v++;              // 17
})(window.Live2DCubismCore);

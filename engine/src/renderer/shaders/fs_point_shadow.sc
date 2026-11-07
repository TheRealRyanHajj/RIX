$input v_shadowWorld

#include <bgfx_shader.sh>

uniform vec4 u_pointShadowLight;

void main()
{
    float radial_depth = length(v_shadowWorld - u_pointShadowLight.xyz) /
                         u_pointShadowLight.w;
    gl_FragColor = vec4_splat(clamp(radial_depth, 0.0, 1.0));
}

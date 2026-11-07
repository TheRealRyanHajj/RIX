$input v_color0, v_normal, v_worldPosition, v_shadowCoord

#include <bgfx_shader.sh>

uniform vec4 u_materialColor;
uniform vec4 u_materialParams;
uniform vec4 u_ambientLight;
uniform vec4 u_directionalLights[4];
uniform vec4 u_directionalColors[4];
uniform vec4 u_pointPositionsRanges[64];
uniform vec4 u_pointColors[64];
uniform vec4 u_spotPositionsRanges[32];
uniform vec4 u_spotDirectionsOuter[32];
uniform vec4 u_spotColorsInner[32];
uniform vec4 u_lightCounts;
uniform vec4 u_cameraPosition;
uniform vec4 u_renderParams;
uniform vec4 u_shadowParams;
SAMPLER2D(s_shadowMap, 1);
uniform mat4 u_spotShadowMatrix;
uniform vec4 u_localShadowFlags;
uniform vec4 u_localShadowParams;
uniform vec4 u_pointShadowLight;
SAMPLER2D(s_spotShadowMap, 7);
SAMPLERCUBE(s_pointShadowMap, 8);

float shadow_visibility(vec4 coordinate)
{
    if (u_renderParams.y < 0.5) {
        return 1.0;
    }
    vec3 projected = coordinate.xyz / coordinate.w;
    if (projected.x < 0.0 || projected.x > 1.0 || projected.y < 0.0 ||
        projected.y > 1.0 || projected.z < 0.0 || projected.z > 1.0) {
        return 1.0;
    }
    float visibility = 0.0;
    for (int y = -1; y <= 1; ++y) {
        for (int x = -1; x <= 1; ++x) {
            float stored = texture2D(
                s_shadowMap,
                projected.xy + vec2(float(x), float(y)) * u_shadowParams.xy).r;
            visibility += projected.z - u_shadowParams.z <= stored ? 1.0 : 0.0;
        }
    }
    return visibility / 9.0;
}

float spot_shadow_visibility(vec3 world_position)
{
    if (u_localShadowFlags.x < 0.5) return 1.0;
    vec4 coordinate = mul(u_spotShadowMatrix, vec4(world_position, 1.0));
    vec3 projected = coordinate.xyz / coordinate.w;
    if (projected.x < 0.0 || projected.x > 1.0 || projected.y < 0.0 ||
        projected.y > 1.0 || projected.z < 0.0 || projected.z > 1.0) return 1.0;
    float visibility = 0.0;
    for (int y = -1; y <= 1; ++y) for (int x = -1; x <= 1; ++x) {
        float stored = texture2D(s_spotShadowMap,
            projected.xy + vec2(float(x), float(y)) * u_localShadowParams.xy).r;
        visibility += projected.z - u_localShadowParams.z <= stored ? 1.0 : 0.0;
    }
    return visibility / 9.0;
}

float point_shadow_visibility(vec3 world_position)
{
    if (u_localShadowFlags.y < 0.5) return 1.0;
    vec3 delta = world_position - u_pointShadowLight.xyz;
    float current = length(delta) / u_pointShadowLight.w;
    float stored = textureCube(s_pointShadowMap, delta).r;
    return current - u_localShadowParams.w <= stored ? 1.0 : 0.35;
}

vec3 direct_light(vec3 base, vec3 normal, vec3 light_direction, vec3 light_color,
                  vec3 view_direction)
{
    float diffuse = max(dot(normal, light_direction), 0.0);
    vec3 legacy = light_color * base * diffuse;
    vec3 halfway_direction = normalize(light_direction + view_direction);
    float roughness = clamp(u_materialParams.z, 0.04, 1.0);
    float shininess = mix(256.0, 4.0, roughness * roughness);
    float specular = diffuse > 0.0
        ? pow(max(dot(normal, halfway_direction), 0.0), shininess)
        : 0.0;
    vec3 f0 = mix(vec3_splat(0.04), base, u_materialParams.y);
    vec3 diffuse_color = base * (1.0 - u_materialParams.y);
    vec3 pbr = light_color * (diffuse_color * diffuse + f0 * specular);
    return mix(legacy, pbr, u_renderParams.x);
}

vec3 shade(vec3 base, vec3 surface_normal, vec3 world_position, float shadow)
{
    vec3 normal = normalize(surface_normal);
    vec3 view_direction = normalize(u_cameraPosition.xyz - world_position);
    vec3 result = u_ambientLight.rgb * base;
    for (int i = 0; i < 4; ++i) {
        if (float(i) >= u_lightCounts.x) break;
        vec3 contribution = direct_light(base, normal,
            -normalize(u_directionalLights[i].xyz), u_directionalColors[i].rgb,
            view_direction);
        result += contribution * (i == 0 ? mix(0.35, 1.0, shadow) : 1.0);
    }
    for (int i = 0; i < 64; ++i) {
        if (float(i) >= u_lightCounts.y) break;
        vec3 delta = u_pointPositionsRanges[i].xyz - world_position;
        float distance_value = length(delta);
        float falloff = clamp(1.0 - distance_value / u_pointPositionsRanges[i].w, 0.0, 1.0);
        float attenuation = falloff * falloff / (1.0 + 0.1 * distance_value * distance_value);
        float local_shadow = i == 0 ? point_shadow_visibility(world_position) : 1.0;
        result += direct_light(base, normal, delta / max(distance_value, 0.0001),
            u_pointColors[i].rgb * attenuation * local_shadow, view_direction);
    }
    for (int i = 0; i < 32; ++i) {
        if (float(i) >= u_lightCounts.z) break;
        vec3 delta = u_spotPositionsRanges[i].xyz - world_position;
        float distance_value = length(delta);
        vec3 to_light = delta / max(distance_value, 0.0001);
        float cone = smoothstep(u_spotDirectionsOuter[i].w,
                                u_spotColorsInner[i].w,
                                dot(-to_light, normalize(u_spotDirectionsOuter[i].xyz)));
        float falloff = clamp(1.0 - distance_value / u_spotPositionsRanges[i].w, 0.0, 1.0);
        float attenuation = cone * falloff * falloff /
                            (1.0 + 0.1 * distance_value * distance_value);
        float local_shadow = i == 0 ? spot_shadow_visibility(world_position) : 1.0;
        result += direct_light(base, normal, to_light,
            u_spotColorsInner[i].rgb * attenuation * local_shadow, view_direction);
    }
    return result;
}

void main()
{
    vec4 base = v_color0 * u_materialColor;
    // bgfx's D3D11 varying reports the surviving outward-wound faces as the
    // false branch for this mesh/cull convention. Preserve outward normals on
    // ordinary geometry and flip only the reverse side of two-sided/front-cull
    // materials.
    float face_sign = gl_FrontFacing ? -1.0 : 1.0;
    vec3 illuminated = shade(base.rgb, v_normal * face_sign, v_worldPosition,
                             shadow_visibility(v_shadowCoord));
    base.rgb = mix(base.rgb, illuminated, u_materialParams.x)
             + base.rgb * u_materialParams.w;
    gl_FragColor = base;
}

uniform mat4 ModelViewProjectionMatrix;
in vec3 pos;
out vec2 uv;

void main()
{
    uv = pos.xy;
    gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);
}
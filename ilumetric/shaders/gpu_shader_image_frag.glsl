uniform sampler2D image;

in vec2 texCoord_interp;
out vec4 fragColor;

void main() {
    fragColor = texture(image, texCoord_interp);
}
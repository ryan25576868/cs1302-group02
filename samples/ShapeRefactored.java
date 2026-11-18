public class Shape {
    private final double width;
    private final double height;
    private final String name;

    public Shape(double width, double height) {
        this(width, height, "shape");
    }

    public Shape(double width, double height, String name) {
        this.width = width;
        this.height = height;
        this.name = name;
    }

    public double area() {
        return width * height;
    }

    public double perimeter() {
        return 2 * (width + height);
    }

    public boolean isSquare() {
        return width == height;
    }

    public String describe() {
        String kind = isSquare() ? "square" : "rectangle";
        return name + " " + kind + " " + width + "x" + height;
    }

    public static void main(String[] args) {
        Shape s = new Shape(4, 4, "tile");
        System.out.println(s.describe());
        System.out.println(s.perimeter());
    }
}

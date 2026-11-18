public class Shape {
    private final double width;
    private final double height;

    public Shape(double width, double height) {
        this.width = width;
        this.height = height;
    }

    public double area() {
        return width * height;
    }

    public String describe() {
        return "Shape " + width + "x" + height;
    }

    public static void main(String[] args) {
        Shape s = new Shape(3, 4);
        System.out.println(s.describe());
    }
}

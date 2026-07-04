@RestController
@RequestMapping("/api/alerts")
class AlertController {
    @GetMapping("/{id}")
    Alert getAlert(Long id) {
        return null;
    }

    @PostMapping(path = {"/search", "/query"})
    List<Alert> search() {
        return List.of();
    }
}

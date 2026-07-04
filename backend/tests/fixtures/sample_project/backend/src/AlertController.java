@RestController
@RequestMapping("/api/alerts")
class AlertController {
    @GetMapping("/{id}")
    Alert getAlert(Long id) {
        return null;
    }

    @PostMapping("/search")
    List<Alert> search() {
        return List.of();
    }
}

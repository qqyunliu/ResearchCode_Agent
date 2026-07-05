@RestController
@RequestMapping("/api/alerts")
class AlertController {
    private final AlertService alertService;

    AlertController(AlertService alertService) {
        this.alertService = alertService;
    }

    @GetMapping("/{id}")
    Alert getAlert(Long id) {
        return alertService.findById(id);
    }

    @PostMapping("/search")
    List<Alert> search() {
        return List.of();
    }
}

package com.example.petstore;

import com.example.petstore.controller.PetController;
import com.example.petstore.repository.PetRepository;
import com.example.petstore.service.PetService;

/** Single production entrypoint. Started only by `java -jar app.jar` (see Dockerfile). */
public class Application {
    public static void main(String[] args) {
        PetRepository repository = new PetRepository();
        PetService service = new PetService(repository);
        PetController controller = new PetController(service);
        System.out.println(controller.listPets());
    }
}

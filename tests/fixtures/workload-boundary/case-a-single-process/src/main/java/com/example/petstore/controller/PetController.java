package com.example.petstore.controller;

import com.example.petstore.service.PetService;

/** Code layer inside the single `Application` process -- not an independent runtime process. */
public class PetController {
    private final PetService petService;

    public PetController(PetService petService) {
        this.petService = petService;
    }

    public String listPets() {
        return petService.findAll();
    }
}

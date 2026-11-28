---
title: "mmWave Radar Fall Detection Device "
github: "https://github.com/engineeringmaxxing/Radar"
description: "Utilising an advanced mmWave Radar chip to generate an estimated projection of the human body to prevent falls.\nI am building this as current surveillance systems in aged care capture audio and video in a manner that is an invasion of privacy for those in aged care facilities. Hopefully by creating this, it can serve as a pioneering technology in  the fall-detection space."
created_at: "2026-11-17"
total_time: "20h"
---

# November 18th, 2026: Architected the system
Today, I worked on planning the system architecture for a human movement monitoring platform that utilises millimetre-wave (mmWave) radar technology.

I discerned a problem: cameras are incredibly INVASIVE - especially in aged care settings where people are trying to live peacefully without having video and audio taped. My solution? Researching the logistics of different radar development platforms, evaluating their suitability for tracking human movement, and investigating these fall-like events. No cameras. No wearable devices.

After comparing several options, I selected the Texas Instruments IWR6843ISK-ODS, a 60 GHz FMCW radar development board capable of producing 3D point-cloud measurements. I chose this platform because it provides access to more detailed spatial and motion information than conventional presence-detection sensors.

In addition to this, I investigated different mounting configurations - particularly the differences between ceiling-mounted and wall-mounted arrangements. From what I could deduce, one of the primary challenges was determining how reliably the radar could observe movement close to the floor, especially when furniture and other obstacles partially obstruct its field of view. Ultimately, I opted for the ceiling mounted configuration.

For processing, I selected a Raspberry Pi 5 (8GB) to handle radar data acquisition, local processing, experimental logging and eventually a real-time visualisation interface. It also provides a basis for future expansion! By having this component as a "super-computer" or a "hub", the aim is to use the current components as a basis for what the technology could look like when the coverage is increased across larger buildings/structures per se.

I established the initial hardware requirements and began planning a custom 3D-printed enclosure and adjustable mounting system. These components will allow me to test different sensor orientations while maintaining consistent mounting geometry.

Finally, I created the GitHub repository to document the project architecture, research objectives and development roadmap.


<img width="922" height="280" alt="image" src="https://fabricate.hackclub-assets.com/1f3ce4182600d5286bce348ed969a73515344a7323d0274197ca483d6f9d6369/image-png/6162f1a4-c2cc-4b93-9541-5d10e727e931.png" />

-----

# November 17, 2026: November 18th, 2026: Architected the system
<!-- fabricate:entry 3336 -->

Today, I worked on planning the system architecture for a human movement monitoring platform that utilises millimetre-wave (mmWave) radar technology.

I discerned a problem: cameras are incredibly INVASIVE - especially in aged care settings where people are trying to live peacefully without having video and audio taped. My solution? Researching the logistics of different radar development platforms, evaluating their suitability for tracking human movement, and investigating these fall-like events. No cameras. No wearable devices.

After comparing several options, I selected the Texas Instruments IWR6843ISK-ODS, a 60 GHz FMCW radar development board capable of producing 3D point-cloud measurements. I chose this platform because it provides access to more detailed spatial and motion information than conventional presence-detection sensors.

In addition to this, I investigated different mounting configurations - particularly the differences between ceiling-mounted and wall-mounted arrangements. From what I could deduce, one of the primary challenges was determining how reliably the radar could observe movement close to the floor, especially when furniture and other obstacles partially obstruct its field of view. Ultimately, I opted for the ceiling mounted configuration. 

For processing, I selected a Raspberry Pi 5 (8GB) to handle radar data acquisition, local processing, experimental logging and eventually a real-time visualisation interface. It also provides a basis for future expansion! By having this component as a "super-computer" or a "hub", the aim is to use the current components as a basis for what the technology could look like when the coverage is increased across larger buildings/structures per se. 

I established the initial hardware requirements and began planning a custom 3D-printed enclosure and adjustable mounting system. These components will allow me to test different sensor orientations while maintaining consistent mounting geometry.

Finally, I created the GitHub repository to document the project architecture, research objectives and development roadmap.
![](https://fabricate.hackclub-assets.com/ed7869b7f498306c975a8739df1d48120d279f6c8a1c91747294ac29f0204297/image-png/image.png)

**Total time spent: 5h**

# November 27, 2026: Started to architect the code required for the project
<!-- fabricate:entry 4045 -->

This was really difficult for an amateur programmer like myself... I had to develop an understanding of TI's (Texas Instruments) UART protocol as well as learning the serial acquisition and recording components. I drafted up some sample code and experimented with potential avenues to go down -  I ended up drafting some code outside of the GitHub repository as I didn't end up finishing it to a degree that I was impressed with. The manual had almost everything I needed to start with but once more, it was a MASSIVE struggle. I look to tomorrow to progress further into binary packet and TLV decoding.


![](https://fabricate.hackclub-assets.com/aeb5476e437ce668b78420d30a3824bb7150d74033e8d816f6bceb8a6c6ed018/image-png/image.png)

**Total time spent: 15h**
